/**
 * Ephe — PWA chat-UX plan, task A4: streamChat() SSE client
 *
 * GIVEN  streamChat() from lib/stream.ts (fetch + ReadableStream, no res.text())
 * WHEN   a fake backend serves different read bounds / frame shapes
 * THEN   events arrive at onEvent in the exact order
 * AND    a frame split over 2 reads is reassembled correctly (no data loss)
 * AND    an unknown event string = no-op (forward-compatible)
 * AND    abort = clean cancellation without an exception
 * AND    non-200 = StreamChatError
 */
import { describe, it, expect, vi, afterAll } from 'vitest'
import { streamChat, StreamChatError } from './stream'
import { seedDeepSettings } from './deepSettings'
import type { DeepSection, StreamEvent } from '../types'

/** Minimal fake body reader: yields the chunks exactly in the given order */
function fakeReader(chunks: Uint8Array[]): ReadableStreamDefaultReader<Uint8Array> {
  let i = 0
  return {
    read: async () => {
      if (i < chunks.length) {
        const value = chunks[i++] as Uint8Array
        return { done: false, value }
      }
      return { done: true, value: undefined }
    },
    cancel: async () => {},
    closed: Promise.resolve(undefined),
    releaseLock: () => {},
  }
}

function frame(obj: unknown): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(obj)}\n\n`)
}

function mockFetch(body: ReadableStreamDefaultReader<Uint8Array>, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Server Error',
    headers: { get: () => 'text/event-stream' },
    body: { getReader: () => body },
  })
}

describe('streamChat (SSE-Client)', () => {
  let collected: StreamEvent[]

  afterAll(() => vi.unstubAllGlobals())

  it('delivers consecutive frames in the exact order', async () => {
    collected = []
    const reader = fakeReader([
      frame({ type: 'thinking_start' }),
      frame({ type: 'chunk', data: 'Hallo ' }),
      frame({ type: 'chunk', data: 'Welt' }),
      frame({ type: 'done' }),
    ])
    vi.stubGlobal('fetch', mockFetch(reader))

    await streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => collected.push(e) })

    expect(collected.map((e) => e.type)).toEqual(['thinking_start', 'chunk', 'chunk', 'done'])
  })

  it('reassembles a frame split across two reads (split safety)', async () => {
    collected = []
    // The complete frame bytes: "data: {\"type\":\"chunk\",\"data\":\"halbes\"}\n\n"
    const full = new TextEncoder().encode(
      'data: ' + JSON.stringify({ type: 'chunk', data: 'halbes' }) + '\n\n',
    )
    const splitAt = 20 // in the middle of the JSON
    const reader = fakeReader([
      full.slice(0, splitAt),
      full.slice(splitAt),
      frame({ type: 'done' }),
    ])
    vi.stubGlobal('fetch', mockFetch(reader))

    await streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => collected.push(e) })

    expect(collected[0]).toEqual({ type: 'chunk', data: 'halbes' })
  })

  it('delivers several frames from a single read', async () => {
    collected = []
    const merged = new Uint8Array([
      ...frame({ type: 'thinking_start' }),
      ...frame({ type: 'done' }),
    ])
    vi.stubGlobal('fetch', mockFetch(fakeReader([merged])))

    await streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => collected.push(e) })

    expect(collected.map((e) => e.type)).toEqual(['thinking_start', 'done'])
  })

  it('ignores SSE comments and keep-alive lines (no event, no crash)', async () => {
    collected = []
    const comment = new TextEncoder().encode(': keep-alive\n\ndata: {"type":"done"}\n\n')
    vi.stubGlobal('fetch', mockFetch(fakeReader([comment])))

    await streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => collected.push(e) })

    expect(collected.map((e) => e.type)).toEqual(['done'])
  })

  it('treats CRLF line endings the same as LF', async () => {
    collected = []
    const crlf = new TextEncoder().encode('data: {"type":"done"}\r\n\r\n')
    vi.stubGlobal('fetch', mockFetch(fakeReader([crlf])))

    await streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => collected.push(e) })

    expect(collected.map((e) => e.type)).toEqual(['done'])
  })

  it('skips broken JSON frames without aborting (defensive parsing)', async () => {
    collected = []
    const broken = new TextEncoder().encode('data: {kaputt\n\ndata: {"type":"done"}\n\n')
    vi.stubGlobal('fetch', mockFetch(fakeReader([broken])))

    await streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => collected.push(e) })

    expect(collected.map((e) => e.type)).toEqual(['done'])
  })

  it('calls reader.cancel() on abort and settles without an exception', async () => {
    const cancel = vi.fn().mockResolvedValue(undefined) // a real reader.cancel() → Promise<void>
    const ac = new AbortController()
    // Realistic fake: read() rejects with an AbortError as soon as the signal is
    // aborted (that is how the real fetch-ReadableStream behaves).
    const reader: ReadableStreamDefaultReader<Uint8Array> = {
      read: () =>
        new Promise((_resolve, reject) => {
          if (ac.signal.aborted) return reject(new DOMException('Aborted', 'AbortError'))
          ac.signal.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          )
        }),
      cancel,
      closed: Promise.resolve(undefined),
      releaseLock: () => {},
    }
    vi.stubGlobal('fetch', mockFetch(reader))

    const p = streamChat({ message: 'Hi', history: [] }, { onEvent: () => {}, signal: ac.signal })
    ac.abort()

    await expect(p).resolves.toBeUndefined()
    // The stream has to actually stop
    await vi.waitFor(() => expect(cancel).toHaveBeenCalled())
  })

  it('throws StreamChatError on non-200 (say, 500)', async () => {
    vi.stubGlobal('fetch', mockFetch(fakeReader([]), false, 500))

    await expect(
      streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }),
    ).rejects.toThrowError(StreamChatError)
  })

  it('posts /api/chat/stream with a JSON body (the contract with chat.py)', async () => {
    const spy = mockFetch(fakeReader([frame({ type: 'done' })]))
    vi.stubGlobal('fetch', spy)

    await streamChat(
      { message: 'Hallo', model: 'gemma4:12b', history: [{ role: 'user', content: 'früher' }] },
      { onEvent: () => {} },
    )

    expect(spy).toHaveBeenCalledTimes(1)
    const call = spy.mock.calls[0] as [string, RequestInit]
    const [url, init] = call
    expect(url).toBe('/api/chat/stream')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    expect(body.message).toBe('Hallo')
    expect(body.model).toBe('gemma4:12b')
    expect(body.history).toEqual([{ role: 'user', content: 'früher' }])
  })
})

// ── I6 P2: keepalive comments while waiting for approval (2026-09-08) ─────
// During the sandbox-approval wait the server sends lines of ': keepalive'.
// Those must produce no events — and since bytes do flow, the idle timeout
// (90s) never fires as the misleading engine-timeout message (stream.ts:64).
describe('SSE keepalive comments (I6 P2)', () => {
  it('ignores comment frames and still delivers the normal events after', async () => {
    const events: StreamEvent[] = []
    const enc = new TextEncoder()
    const spy = mockFetch(
      fakeReader([
        enc.encode(': keepalive\n\n'),
        frame({ type: 'chunk', data: 'a' }),
        enc.encode(': keepalive\n\n: keepalive\n\n'),
        frame({ type: 'done' }),
      ]),
    )
    vi.stubGlobal('fetch', spy)
    await streamChat({ message: 'x', history: [] }, { onEvent: (e) => events.push(e) })
    expect(events.map((e) => e.type)).toEqual(['chunk', 'done'])
  })
})

/* S19: the terminal frame decides the turn, not the transport. */
function failingReader(chunks: Uint8Array[], err: unknown = new TypeError('network down')) {
  let i = 0
  return {
    read: async () => {
      if (i < chunks.length) return { done: false, value: chunks[i++] as Uint8Array }
      throw err
    },
    cancel: async () => {},
    closed: Promise.resolve(undefined),
    releaseLock: () => {},
  } as unknown as ReadableStreamDefaultReader<Uint8Array>
}

describe('S19 terminal handling', () => {
  it('a read error after the done frame is not a failed turn', async () => {
    vi.stubGlobal('fetch', mockFetch(failingReader([frame({ type: 'done' })])))
    await expect(
      streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }),
    ).resolves.toBeUndefined()
  })

  it('a network read error is coded as network', async () => {
    vi.stubGlobal('fetch', mockFetch(failingReader([frame({ type: 'chunk', data: 't' })])))
    await expect(
      streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }),
    ).rejects.toMatchObject({ code: 'network' })
  })

  it('any other read error before a terminal frame carries stream_closed_before_done', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(failingReader([frame({ type: 'chunk', data: 't' })], new Error('boom'))),
    )
    await expect(
      streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }),
    ).rejects.toMatchObject({ code: 'stream_closed_before_done' })
  })

  it('a clean end without a terminal frame is a failed turn', async () => {
    vi.stubGlobal('fetch', mockFetch(fakeReader([frame({ type: 'chunk', data: 't' })])))
    await expect(
      streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }),
    ).rejects.toMatchObject({ code: 'stream_closed_before_done' })
  })

  it('an error frame ends the turn; a later read error adds nothing', async () => {
    const events: StreamEvent[] = []
    vi.stubGlobal(
      'fetch',
      mockFetch(
        failingReader([frame({ type: 'error', msg: 'nope', reason_code: 'engine_error' })]),
      ),
    )
    await expect(
      streamChat({ message: 'Hi', history: [] }, { onEvent: (e) => events.push(e) }),
    ).resolves.toBeUndefined()
    expect(events.map((e) => e.type)).toEqual(['error'])
  })

  it('the HTTP error keeps its status and code', async () => {
    vi.stubGlobal('fetch', mockFetch(fakeReader([]), false, 503))
    const err = await streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }).catch(
      (e) => e,
    )
    expect(err).toBeInstanceOf(StreamChatError)
    expect(err.status).toBe(503)
    expect(err.code).toBe('http_error')
  })

  it('an idle timeout keeps its own code', async () => {
    const silent = {
      read: () => new Promise(() => {}),
      cancel: async () => {},
      closed: Promise.resolve(undefined),
      releaseLock: () => {},
    } as unknown as ReadableStreamDefaultReader<Uint8Array>
    vi.stubGlobal('fetch', mockFetch(silent))
    const err = await streamChat(
      { message: 'Hi', history: [] },
      { onEvent: () => {}, idleTimeoutMs: 10 },
    ).catch((e) => e)
    expect(err.code).toBe('idle_timeout')
  })
})

/**
 * The register's own dial. Neither case passes `idleTimeoutMs`, so the bound can
 * only come from `chat.stream_idle_seconds` — which is the difference between a
 * control and a label that sits next to a constant.
 */
describe('the idle bound comes from the register', () => {
  function silentReader(): ReadableStreamDefaultReader<Uint8Array> {
    return {
      read: () => new Promise(() => {}),
      cancel: async () => {},
      closed: Promise.resolve(undefined),
      releaseLock: () => {},
    } as unknown as ReadableStreamDefaultReader<Uint8Array>
  }

  function seedIdleSeconds(value: number) {
    seedDeepSettings([
      {
        key: 'chat',
        fields: [
          {
            key: 'chat.stream_idle_seconds',
            type: 'number',
            label: 'Abort stream after silence (s)',
            labelEn: 'Abort stream after silence (s)',
            default: 60,
            value,
            min: 10,
            max: 600,
          },
        ],
      },
    ] as unknown as DeepSection[])
  }

  /** One stalled stream plus fake timers; `settle()` reads the outcome without awaiting. */
  function startStalled() {
    vi.stubGlobal('fetch', mockFetch(silentReader()))
    let outcome: unknown = 'pending'
    const running = streamChat({ message: 'Hi', history: [] }, { onEvent: () => {} }).catch(
      (e) => e,
    )
    void running.then((e) => {
      outcome = e
    })
    return {
      settle: () => outcome,
      advance: (ms: number) => vi.advanceTimersByTimeAsync(ms),
    }
  }

  it('waits the seconds the register names, not the default', async () => {
    vi.useFakeTimers()
    try {
      seedIdleSeconds(10)
      const stalled = startStalled()
      await stalled.advance(9_900)
      expect(stalled.settle()).toBe('pending')
      await stalled.advance(400)
      const settled = stalled.settle()
      expect(settled).toBeInstanceOf(StreamChatError)
      expect((settled as StreamChatError).code).toBe('idle_timeout')
    } finally {
      vi.useRealTimers()
      seedDeepSettings(null)
    }
  })

  it('leaves a stall alone until the shipped sixty seconds are over', async () => {
    vi.useFakeTimers()
    try {
      seedDeepSettings(null)
      const stalled = startStalled()
      await stalled.advance(30_000)
      expect(stalled.settle()).toBe('pending')
      await stalled.advance(30_200)
      const settled = stalled.settle()
      expect(settled).toBeInstanceOf(StreamChatError)
      expect((settled as StreamChatError).code).toBe('idle_timeout')
    } finally {
      vi.useRealTimers()
      seedDeepSettings(null)
    }
  })
})
