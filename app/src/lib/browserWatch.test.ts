/**
 * #88 — what the watch client reports, from the bytes the route sends.
 *
 * The transport is `fetch` with a reader, so these cases drive that reader with a
 * `ReadableStream` of the exact SSE frames `server/routes/browser_watch.py` writes. The
 * states are the deliverable here: a pane that only ever shows a picture cannot tell a
 * stalled run apart from a calm page, and only this state machine can.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  STILL_AFTER_SECONDS,
  watchBrowserSession,
  watchSnapshot,
  type WatchSnapshot,
} from './browserWatch'

/** One SSE frame in the shape the route emits: `event: <name>\ndata: <json>\n\n`. */
function sse(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
}

/**
 * A stream of SSE chunks. `hold` keeps it open, which is what a real cast does: the route
 * ends when its reader leaves. A stream that closed at once would exercise the reconnect
 * path instead of this one, and its abort would land on nothing.
 */
function streamOf(chunks: string[], hold = true): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      if (!hold) controller.close()
    },
  })
}

function answerOk(chunks: string[], hold = true) {
  return vi.fn(
    async () => ({ ok: true, status: 200, body: streamOf(chunks, hold) }) as unknown as Response,
  )
}

function answerError(status: number, body: unknown, jsonFails = false) {
  return vi.fn(
    async () =>
      ({
        ok: false,
        status,
        json: async () => {
          if (jsonFails) throw new Error('not json')
          return body
        },
      }) as unknown as Response,
  )
}

/** The client awaits a microtask per read and one timer per reconnect; this outlasts both. */
async function flush(): Promise<void> {
  for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setTimeout(resolve, 0))
}

/** Subscribe, let the client read what it was handed, then leave. */
async function collect(
  session: string,
  chunks: string[],
): Promise<{ snapshots: WatchSnapshot[]; aborts: number }> {
  vi.stubGlobal('fetch', answerOk(chunks))
  const snapshots: WatchSnapshot[] = []
  let aborts = 0
  const originalAbort = AbortController.prototype.abort
  AbortController.prototype.abort = function patched(this: AbortController) {
    aborts += 1
    return originalAbort.call(this)
  }
  const unsubscribe = watchBrowserSession(session, (snapshot) => snapshots.push(snapshot))
  await flush()
  unsubscribe()
  AbortController.prototype.abort = originalAbort
  return { snapshots, aborts }
}

const FRAME = {
  jpeg: 'aGVsbG8=',
  viewport_width: 1280,
  viewport_height: 800,
  cast_width: 800,
  cast_height: 500,
  scroll: 40,
  scale: 1,
  page_top: 0,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the watch client reads the stream the route writes', () => {
  it('starts at connecting and names the page once a frame arrives', async () => {
    const { snapshots } = await collect('bw-live', [
      sse('status', { state: 'casting', session: 'bw-live' }),
      sse('frame', FRAME),
    ])

    expect(snapshots.map((snapshot) => snapshot.phase)).toContain('connecting')
    expect(snapshots.at(-1)?.phase).toBe('casting')
    expect(snapshots.at(-1)?.frame?.jpeg).toBe('aGVsbG8=')
  })

  it('keeps the page space and the cast space apart', async () => {
    const { snapshots } = await collect('bw-spaces', [sse('frame', FRAME)])

    expect(snapshots.at(-1)?.frame).toMatchObject({
      viewportWidth: 1280,
      viewportHeight: 800,
      castWidth: 800,
      castHeight: 500,
      scroll: 40,
      audit: null,
    })
  })

  it('keeps a frame with no audit row unproven and reads a row when one is present', async () => {
    const bare = await collect('bw-bare', [sse('frame', FRAME)])
    expect(bare.snapshots.at(-1)?.frame?.audit).toBeNull()

    const bound = await collect('bw-bound', [
      sse('frame', {
        ...FRAME,
        audit: {
          kind: 'tool_exec',
          ts: '2026-11-07T12:00:00.000Z',
          tool: 'browser_go',
          verdict: 'observed',
          delta: { url_changed: 1 },
        },
      }),
    ])
    expect(bound.snapshots.at(-1)?.frame?.audit).toMatchObject({
      kind: 'tool_exec',
      tool: 'browser_go',
      verdict: 'observed',
    })
  })

  /** The point of the keepalive: a still page must read as still, above the noise floor. */
  it('calls a calm page live and a long pause unchanged', async () => {
    const calm = await collect('bw-calm', [
      sse('frame', FRAME),
      sse('keepalive', { since_frame_s: 2 }),
    ])
    expect(calm.snapshots.at(-1)?.phase).toBe('casting')
    expect(calm.snapshots.at(-1)?.ageS).toBe(2)

    const still = await collect('bw-still', [
      sse('frame', FRAME),
      sse('keepalive', { since_frame_s: STILL_AFTER_SECONDS + 1 }),
    ])
    expect(still.snapshots.at(-1)?.phase).toBe('unchanged')
    // The frame stays: a pane that goes blank when the page stops moving would look broken.
    expect(still.snapshots.at(-1)?.frame?.jpeg).toBe('aGVsbG8=')
  })

  it('says the session is missing before anything is cast, and quotes the reason', async () => {
    vi.stubGlobal(
      'fetch',
      answerError(404, {
        error: {
          reason_code: 'browser_session_unknown',
          reason_params: { session: 'bw-ghost' },
          message: "no browser session 'bw-ghost' is open to watch",
        },
      }),
    )
    const snapshots: WatchSnapshot[] = []
    watchBrowserSession('bw-ghost', (snapshot) => snapshots.push(snapshot))
    await flush()

    expect(snapshots.at(-1)?.phase).toBe('refused')
    expect(snapshots.at(-1)?.refusal).toMatchObject({
      code: 'browser_session_unknown',
      params: { session: 'bw-ghost' },
    })
  })

  it('carries the engine reason when the cast will not start', async () => {
    vi.stubGlobal(
      'fetch',
      answerError(409, {
        error: {
          reason_code: 'browser_watch_unavailable',
          reason_params: { reason: 'TimeoutError' },
          message: 'this browser session cannot send its frames right now: TimeoutError',
        },
      }),
    )
    const snapshots: WatchSnapshot[] = []
    watchBrowserSession('bw-nocast', (snapshot) => snapshots.push(snapshot))
    await flush()

    expect(snapshots.at(-1)?.refusal?.params).toEqual({ reason: 'TimeoutError' })
    expect(snapshots.at(-1)?.phase).toBe('refused')
  })

  it('falls back to the status when an error body carries no code', async () => {
    vi.stubGlobal('fetch', answerError(500, {}, true))
    const snapshots: WatchSnapshot[] = []
    watchBrowserSession('bw-500', (snapshot) => snapshots.push(snapshot))
    await flush()

    expect(snapshots.at(-1)?.refusal).toMatchObject({ code: 'http_500' })
  })

  it('ignores a data line it cannot parse and keeps the last true state', async () => {
    const { snapshots } = await collect('bw-junk', [
      sse('frame', FRAME),
      'event: frame\ndata: {not json\n\n',
    ])

    expect(snapshots.at(-1)?.phase).toBe('casting')
    expect(snapshots.at(-1)?.frame?.jpeg).toBe('aGVsbG8=')
  })

  /** The rule the cast is paced by: nobody watching means nobody pays for the frames. */
  it('closes the stream when the last listener leaves and drops the session', async () => {
    const { aborts } = await collect('bw-close', [sse('status', { state: 'casting' })])

    expect(aborts).toBe(1)
    expect(watchSnapshot('bw-close')).toBeNull()
  })

  it('hands a second listener the state that is already true', async () => {
    // held open: the first listener is still watching when the second arrives
    vi.stubGlobal('fetch', answerOk([sse('frame', FRAME)]))
    const first: WatchSnapshot[] = []
    const unsubscribe = watchBrowserSession('bw-share', (snapshot) => first.push(snapshot))
    await flush()
    expect(first.at(-1)?.frame?.jpeg).toBe('aGVsbG8=')

    const second: WatchSnapshot[] = []
    const unsubscribeTwo = watchBrowserSession('bw-share', (snapshot) => second.push(snapshot))
    // The callback runs synchronously on subscribe, before any read could have completed.
    expect(second[0]?.phase).toBe('casting')
    expect(second[0]?.frame?.jpeg).toBe('aGVsbG8=')

    unsubscribe()
    unsubscribeTwo()
  })
})
