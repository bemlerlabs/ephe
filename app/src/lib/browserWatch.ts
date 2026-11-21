/**
 * #88 — the client for a watched browser session.
 *
 * `GET /api/browser/watch/{session}` answers a run's own page as JPEG frames. This module
 * turns that stream into the one thing the surface needs: a state that distinguishes
 * *the page is moving* from *the page is still* from *this session cannot be watched, and
 * here is why*.
 *
 * Why `fetch` with a reader instead of `EventSource`, when `multiplex.ts` established the
 * other pattern for this app: `EventSource` cannot read a response body that is not a
 * stream, and the route's two refusals (`browser_session_unknown` 404,
 * `browser_watch_unavailable` 409) arrive as an error envelope with a reason code and the
 * engine's own sentence. Over `EventSource` those collapse into one anonymous connection
 * error, which is exactly the state this surface must not show. The reader costs a manual
 * frame parser (the shape `stream.ts` already uses) and a bounded reconnect, and it buys
 * the reason.
 *
 * The reconnect is bounded for the same reason the cast is paced: a session that ended
 * would otherwise be retried forever, and a running cast costs a real share of a core.
 */
import { apiUrl } from '@/lib/api'

/** The audit row a frame is allowed to stand beside. Absent means the frame is unproven. */
export interface WatchAudit {
  kind: string
  ts: string
  tool: string
  verdict: 'observed' | 'unproven'
  delta: Record<string, number>
}

/** One frame, with the two coordinate spaces the engine reports (see `core/browser.py`). */
export interface WatchFrame {
  jpeg: string
  viewportWidth: number
  viewportHeight: number
  castWidth: number
  castHeight: number
  scroll: number
  scale: number
  pageTop: number
  /** Null when this picture was taken with no browser `tool_exec` on the session. */
  audit: WatchAudit | null
}

/** The refusal as the route sent it: a code, its slots, and the sentence behind them. */
export interface WatchRefusal {
  code: string
  message: string
  /** The `reason_params` the registry sends beside the code, so the surface fills its own
   *  words from the reader's bundle instead of showing the server's English. */
  params: Record<string, string>
}

export type WatchPhase = 'connecting' | 'casting' | 'unchanged' | 'refused' | 'ended'

export interface WatchSnapshot {
  phase: WatchPhase
  /** The newest frame, kept after it ages so the pane shows the page rather than a hole. */
  frame: WatchFrame | null
  /** Seconds since the newest frame, from the server's own count. */
  ageS: number
  refusal: WatchRefusal | null
}

type Listener = (snapshot: WatchSnapshot) => void

/**
 * How long a pane may show nothing new before it says the page is still.
 *
 * Measured: frames are damage-driven, an animating page ran 93 fps and a still one produced
 * about one every two seconds. A threshold near the server's 2 s keepalive would flip to
 * `unchanged` on a page that is merely calm, so the number sits above that noise.
 */
export const STILL_AFTER_SECONDS = 5

/** Retries after a stream that ended without a refusal, and the pause between them. */
const RECONNECT_LIMIT = 3
const RECONNECT_DELAY_MS = 1000

function toAudit(value: unknown): WatchAudit | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const kind = typeof row.kind === 'string' ? row.kind : ''
  const ts = typeof row.ts === 'string' ? row.ts : ''
  if (!kind || !ts) return null
  const delta: Record<string, number> = {}
  if (row.delta && typeof row.delta === 'object') {
    for (const [key, item] of Object.entries(row.delta as Record<string, unknown>)) {
      if (typeof item === 'number' && Number.isFinite(item)) delta[key] = item
    }
  }
  return {
    kind,
    ts,
    tool: typeof row.tool === 'string' ? row.tool : '',
    verdict: row.verdict === 'observed' ? 'observed' : 'unproven',
    delta,
  }
}

function toFrame(data: Record<string, unknown>): WatchFrame {
  const num = (key: string, fallback: number): number => {
    const value = Number(data[key])
    return Number.isFinite(value) ? value : fallback
  }
  return {
    jpeg: String(data.jpeg ?? ''),
    viewportWidth: num('viewport_width', 0),
    viewportHeight: num('viewport_height', 0),
    castWidth: num('cast_width', 0),
    castHeight: num('cast_height', 0),
    scroll: num('scroll', 0),
    scale: num('scale', 1),
    pageTop: num('page_top', 0),
    audit: toAudit(data.audit),
  }
}

/** The stream for one session, shared by every pane that watches it. */
class WatchStream {
  private listeners = new Set<Listener>()
  private controller: AbortController | null = null
  private snapshot: WatchSnapshot = { phase: 'connecting', frame: null, ageS: 0, refusal: null }
  private attempts = 0
  private running = false

  constructor(private readonly session: string) {}

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    // A late pane is handed the state that is already true, so it never draws a blank while
    // the stream that is already running waits for the next change.
    listener(this.snapshot)
    if (!this.running) void this.run()
    return () => {
      this.listeners.delete(listener)
      if (this.listeners.size === 0) this.stop()
    }
  }

  empty(): boolean {
    return this.listeners.size === 0
  }

  /** The state as it stands, for a surface that arrives while the stream is already open. */
  current(): WatchSnapshot {
    return this.snapshot
  }

  private emit(next: Partial<WatchSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...next }
    for (const listener of [...this.listeners]) listener(this.snapshot)
  }

  private stop(): void {
    this.controller?.abort()
    this.controller = null
    this.attempts = 0
    this.running = false
  }

  private async run(): Promise<void> {
    if (this.running) return
    this.running = true
    this.controller = new AbortController()
    let ended = false
    try {
      const response = await fetch(
        apiUrl(`/api/browser/watch/${encodeURIComponent(this.session)}`),
        { headers: { Accept: 'text/event-stream' }, signal: this.controller.signal },
      )
      if (!response.ok) {
        // The refusal is the payload: the route says which session is missing and what the
        // engine answered, and the pane shows that instead of a blank box.
        this.emit({ phase: 'refused', refusal: await readRefusal(response), ageS: 0 })
        this.running = false
        return
      }
      if (!response.body) {
        this.emit({ phase: 'ended', refusal: null })
        this.running = false
        return
      }
      await this.read(response.body)
      ended = true
    } catch {
      // An aborted read is this module closing the stream, which is not a fault to report.
    }
    this.controller = null
    this.running = false
    if (this.listeners.size === 0) return
    if (ended && this.attempts < RECONNECT_LIMIT) {
      this.attempts += 1
      this.emit({ phase: 'connecting' })
      await delay(RECONNECT_DELAY_MS)
      if (this.listeners.size > 0) void this.run()
      return
    }
    this.attempts = 0
    this.emit({ phase: 'ended' })
  }

  /** `\n\n`-delimited frames, assembled across reads the way `stream.ts` does it. */
  private async read(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })
      let cut = buffer.indexOf('\n\n')
      while (cut >= 0) {
        this.apply(buffer.slice(0, cut))
        buffer = buffer.slice(cut + 2)
        cut = buffer.indexOf('\n\n')
      }
    }
  }

  private apply(chunk: string): void {
    let name = 'message'
    let data = ''
    for (const line of chunk.split('\n')) {
      if (line.startsWith('event: ')) name = line.slice(7).trim()
      else if (line.startsWith('data: ')) data = line.slice(6)
    }
    if (!data) return
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(data) as Record<string, unknown>
    } catch {
      return
    }
    if (name === 'status') {
      this.attempts = 0
      this.emit({ phase: 'casting', refusal: null, ageS: 0 })
    } else if (name === 'frame') {
      this.attempts = 0
      this.emit({ phase: 'casting', frame: toFrame(payload), ageS: 0 })
    } else if (name === 'keepalive') {
      const raw = Number(payload.since_frame_s ?? 0)
      const age = Number.isFinite(raw) ? raw : 0
      this.emit({
        ageS: age,
        phase: age >= STILL_AFTER_SECONDS && this.snapshot.frame ? 'unchanged' : 'casting',
      })
    }
  }
}

async function readRefusal(response: Response): Promise<WatchRefusal> {
  const status = `http_${response.status}`
  const fallback: WatchRefusal = {
    code: status,
    message: `the watch channel answered ${response.status}`,
    params: {},
  }
  try {
    const body = (await response.json()) as {
      error?: { reason_code?: string; message?: string; reason_params?: Record<string, unknown> }
    }
    const error = body.error ?? {}
    return {
      code: String(error.reason_code ?? status),
      message: String(error.message ?? fallback.message),
      params: Object.fromEntries(
        Object.entries(error.reason_params ?? {}).map(([key, value]) => [key, String(value)]),
      ),
    }
  } catch {
    return fallback
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const streams = new Map<string, WatchStream>()

/**
 * Watch one browser session. Returns the unsubscribe; the last listener out closes the
 * stream, which is what tells the server nobody is looking any more.
 */
export function watchBrowserSession(session: string, listener: Listener): () => void {
  let stream = streams.get(session)
  if (!stream) {
    stream = new WatchStream(session)
    streams.set(session, stream)
  }
  const own = stream
  const unsubscribe = own.subscribe(listener)
  return () => {
    unsubscribe()
    // Dropping the map entry is what lets the next watch rebuild it: a closed stream that
    // stayed here would be reused in its stopped state and never reconnect.
    if (own.empty()) streams.delete(session)
  }
}

/** The state a test or a second surface reads without opening a stream of its own. */
export function watchSnapshot(session: string): WatchSnapshot | null {
  return streams.get(session)?.current() ?? null
}
