/**
 * C1: every way a stream can end leaves exactly one content-free diagnostic.
 *
 * The line is the only client-side record of why a turn's connection closed
 * (no persisted client channel exists for transport facts), so each forced
 * close below names the reason, the frame the reader was on, the elapsed time
 * and whether a terminal frame ever arrived — never prompt or answer text.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STREAM_DIAG_PREFIX, StreamChatError, streamChat } from './stream'

type Step = Uint8Array | 'end' | { error: unknown }

function frame(obj: unknown): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(obj)}\n\n`)
}

function scriptedReader(steps: Step[]): ReadableStreamDefaultReader<Uint8Array> {
  let i = 0
  return {
    read: async () => {
      const step = steps[i++]
      if (step === undefined || step === 'end') return { done: true, value: undefined }
      if (step !== null && typeof step === 'object' && 'error' in step) throw step.error
      return { done: false, value: step as Uint8Array }
    },
    cancel: async () => {},
    closed: Promise.resolve(undefined),
    releaseLock: () => {},
  } as unknown as ReadableStreamDefaultReader<Uint8Array>
}

function mockFetch(reader: ReadableStreamDefaultReader<Uint8Array>, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Server Error',
    headers: { get: () => 'text/event-stream' },
    body: { getReader: () => reader },
  })
}

function captureDebug(): string[] {
  const lines: string[] = []
  vi.spyOn(console, 'debug').mockImplementation((...args: unknown[]) => {
    lines.push(args.map(String).join(' '))
  })
  return lines
}

function readDiagnostic(lines: string[]) {
  expect(lines).toHaveLength(1)
  const line = lines[0] as string
  expect(line.startsWith(STREAM_DIAG_PREFIX)).toBe(true)
  return JSON.parse(line.slice(STREAM_DIAG_PREFIX.length + 1)) as Record<string, unknown>
}

const FIELDS = [
  'close_reason',
  'close_code',
  'last_frame_type',
  'elapsed_ms',
  'terminal_seen',
  'turn_id',
]

describe('streamChat close diagnostic', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('reports a terminal done frame with the frame that closed the turn', async () => {
    const lines = captureDebug()
    vi.stubGlobal(
      'fetch',
      mockFetch(scriptedReader([frame({ type: 'chunk', data: 'answer' }), frame({ type: 'done' }), 'end'])),
    )

    await streamChat({ message: 'question', history: [] }, { onEvent: () => {} })

    const diag = readDiagnostic(lines)
    expect(Object.keys(diag).sort()).toEqual([...FIELDS].sort())
    expect(diag.close_reason).toBe('terminal')
    expect(diag.close_code).toBe('done')
    expect(diag.last_frame_type).toBe('done')
    expect(diag.terminal_seen).toBe(true)
    expect(typeof diag.elapsed_ms).toBe('number')
  })

  it('reports an error frame as the terminal frame', async () => {
    const lines = captureDebug()
    vi.stubGlobal(
      'fetch',
      mockFetch(scriptedReader([frame({ type: 'error', msg: 'engine went away' }), 'end'])),
    )

    await streamChat({ message: 'question', history: [] }, { onEvent: () => {} })

    const diag = readDiagnostic(lines)
    expect(diag.close_reason).toBe('terminal')
    expect(diag.close_code).toBe('error')
    expect(diag.terminal_seen).toBe(true)
  })

  it('reports an abort before any terminal frame and resolves cleanly', async () => {
    const lines = captureDebug()
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' })
    vi.stubGlobal('fetch', mockFetch(scriptedReader([frame({ type: 'chunk', data: 'half' }), { error: abort }])))
    const controller = new AbortController()
    controller.abort()

    await streamChat(
      { message: 'question', history: [] },
      { onEvent: () => {}, signal: controller.signal },
    )

    const diag = readDiagnostic(lines)
    expect(diag.close_reason).toBe('abort')
    expect(diag.last_frame_type).toBe('chunk')
    expect(diag.terminal_seen).toBe(false)
  })

  it('reports the idle timeout that ended the read', async () => {
    const lines = captureDebug()
    // No source ever enqueues or closes: every read() hangs, as a silent engine does.
    vi.stubGlobal('fetch', mockFetch(new ReadableStream<Uint8Array>().getReader()))

    await expect(
      streamChat({ message: 'question', history: [] }, { onEvent: () => {}, idleTimeoutMs: 10 }),
    ).rejects.toBeInstanceOf(StreamChatError)

    const diag = readDiagnostic(lines)
    expect(diag.close_reason).toBe('idle_timeout')
    expect(diag.close_code).toBe('idle_timeout')
    expect(diag.terminal_seen).toBe(false)
  })

  it('reports a read error before the terminal frame and still throws', async () => {
    const lines = captureDebug()
    vi.stubGlobal(
      'fetch',
      mockFetch(scriptedReader([frame({ type: 'chunk', data: 'half' }), { error: new Error('socket reset') }])),
    )

    await expect(
      streamChat({ message: 'question', history: [] }, { onEvent: () => {} }),
    ).rejects.toMatchObject({ code: 'stream_closed_before_done' })

    const diag = readDiagnostic(lines)
    expect(diag.close_reason).toBe('read_error')
    expect(diag.close_code).toBe('stream_closed_before_done')
    expect(diag.last_frame_type).toBe('chunk')
    expect(diag.terminal_seen).toBe(false)
  })

  it('reports an EOF without a terminal frame', async () => {
    const lines = captureDebug()
    vi.stubGlobal('fetch', mockFetch(scriptedReader([frame({ type: 'chunk', data: 'half' }), 'end'])))

    await expect(
      streamChat({ message: 'question', history: [] }, { onEvent: () => {} }),
    ).rejects.toMatchObject({ code: 'stream_closed_before_done' })

    const diag = readDiagnostic(lines)
    expect(diag.close_reason).toBe('eof_before_terminal')
    expect(diag.terminal_seen).toBe(false)
  })

  it('reports a fetch that never got a response as a network close', async () => {
    const lines = captureDebug()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(
      streamChat({ message: 'question', history: [] }, { onEvent: () => {} }),
    ).rejects.toBeInstanceOf(TypeError)

    const diag = readDiagnostic(lines)
    expect(diag.close_reason).toBe('network')
    expect(diag.last_frame_type).toBe('')
    expect(diag.terminal_seen).toBe(false)
  })

  it('carries the turn id so the client line and the server ledger correlate', async () => {
    const lines = captureDebug()
    vi.stubGlobal(
      'fetch',
      mockFetch(
        scriptedReader([
          frame({ type: 'turn', turn_id: 'turn-2026-10-25-1838' }),
          frame({ type: 'chunk', data: 'half' }),
          { error: new Error('socket reset') },
        ]),
      ),
    )

    await expect(
      streamChat({ message: 'question', history: [] }, { onEvent: () => {} }),
    ).rejects.toBeInstanceOf(StreamChatError)

    const diag = readDiagnostic(lines)
    expect(diag.turn_id).toBe('turn-2026-10-25-1838')
  })

  it('keeps prompt and answer text out of the line', async () => {
    const lines = captureDebug()
    const prompt = 'PROMPT-SENTINEL-7f3a'
    const answer = 'ANSWER-SENTINEL-2c9d'
    vi.stubGlobal(
      'fetch',
      mockFetch(
        scriptedReader([
          frame({ type: 'chunk', data: answer }),
          { error: new Error('socket reset') },
        ]),
      ),
    )

    await expect(
      streamChat({ message: prompt, history: [] }, { onEvent: () => {} }),
    ).rejects.toBeInstanceOf(StreamChatError)

    expect(lines[0]).not.toContain(prompt)
    expect(lines[0]).not.toContain(answer)
  })
})
