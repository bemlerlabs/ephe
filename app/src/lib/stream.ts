/**
 * Ephe — SSE stream client (PWA chat UX plan, task A4)
 *
 * POST /api/chat/stream + fetch/ReadableStream (not EventSource: we need
 * a POST body + custom headers). Live streaming: we read the response
 * byte-for-byte and parse SSE frames ACROSS read boundaries — a frame may
 * span several `reader.read()` calls.
 *
 * SSE format (server/routes/chat.py):
 *   data: {"type": "...", ...}\n\n
 * (no event: field, no id: lines; keep-alive comments ": ..." are allowed
 * and ignored.)
 *
 * Error semantics:
 *  - HTTP status ≠ 2xx          → StreamChatError (before the first event)
 *  - stream breaks mid turn     → AbortError (if the signal aborted),
 *    otherwise StreamChatError("Streamabbruch")
 *  - abort (stop button)        → resolves cleanly, the reader is cancelled
 *  - broken JSON frame          → frame skipped (defensive, no abort)
 *  - unknown event string       → no-op (forward compatible, reducer trust)
 */
import type { StreamChatRequest, StreamEvent } from '../types'

export class StreamChatError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'StreamChatError'
  }
}

export interface StreamChatOptions {
  /** Called for EVERY parsed event (including unknown events — reducer no-ops) */
  onEvent: (event: StreamEvent) => void
  /** AbortSignal (stop button): cancels the in-flight stream */
  signal?: AbortSignal
  /**
   * Idle timeout: throws StreamChatError when the server sends ABSOLUTELY no
   * byte for that long. Guards against the "spinner spins forever" case: a
   * hanging LLM await (e.g. reflect/revision against a dead engine) sends
   * neither done nor an error — without this timeout reader.read() blocks
   * forever. Resets on EVERY byte, so it measures real silence, not total duration.
   */
  idleTimeoutMs?: number
}

// W18 parity: reference A stale_timeout_seconds=60 → identical idle threshold.
// I6-3: the threshold is a control (`chat.stream_idle_seconds`, default 60).
// It is read at the point of use instead of in an import constant — a constant
// would freeze at the first import and saving in the panel would stay without
// effect until reload.
const IDLE_TIMEOUT_DEFAULT_S = 60

/** reader.read(), but with an idle timeout: throws when no byte arrives for ms. */
export function readWithIdle(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  ms: number,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timer: ReturnType<typeof setTimeout>
  const idle = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new StreamChatError('Zeitüberschreitung: keine Antwort der Engine')),
      ms,
    )
  })
  // ponytail: a per-byte reset is enough; a per-stream watchdog + heartbeat
  // only once legitime reflect/revision awaits measurably need >90s.
  return Promise.race([reader.read(), idle]).finally(() => clearTimeout(timer))
}

// Desktop wave: the same BASE_URL resolution as the API client (Tauri shell
// → local product server), otherwise the SSE stream stays same-origin into nothing.
import { DESKTOP_BASE_URL as BASE_URL } from './desktopBaseUrl'
import { deepNumber } from './deepSettings'

/**
 * Opens the SSE stream for a chat message.
 *
 * Resolves once the `done` event has been processed OR the server closed the
 * stream. Throws StreamChatError on HTTP error/abort.
 * @throws StreamChatError
 */
export async function streamChat(req: StreamChatRequest, opts: StreamChatOptions): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(req),
    signal: opts.signal,
  })

  if (!res.ok || !res.body) {
    // P9-F2 (round 14): the raw status code does not belong in the visible
    // error line — the diagnosis stays available via `status`.
    throw new StreamChatError('Der Stream konnte nicht gestartet werden', res.status)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  const idleMs =
    opts.idleTimeoutMs ?? deepNumber('chat.stream_idle_seconds', IDLE_TIMEOUT_DEFAULT_S) * 1000

  try {
    for (;;) {
      const { done, value } = await readWithIdle(reader, idleMs)
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE frames are separated by an empty double line ("\n\n", CRLF:
      // "\r\n\r\n"). Whatever comes AFTER the last separator is a
      // (possible) partial frame and stays in the buffer for the next read.
      for (;;) {
        const a = buffer.indexOf('\n\n')
        const b = buffer.indexOf('\r\n\r\n')
        let sep = -1
        let consumed = 2
        if (a !== -1 && (b === -1 || a < b)) {
          sep = a
        } else if (b !== -1) {
          sep = b
          consumed = 4
        }
        if (sep === -1) break
        const raw = buffer.slice(0, sep)
        buffer = buffer.slice(sep + consumed)
        for (const event of parseSseBlock(raw)) {
          opts.onEvent(event)
        }
      }
    }

    // Tail flush: at the end of the stream a frame may still sit there without
    // a final "\n\n" (defensive — the backend closes correctly, but we do not
    // want to leave a last frame stuck in the buffer).
    if (buffer.trim()) {
      for (const event of parseSseBlock(buffer)) {
        opts.onEvent(event)
      }
    }
  } catch (err) {
    // P0-3: tail flush ALSO on the error/abort path — the flush standing after
    // the loop inside the try is skipped on abort (a readWithIdle throw),
    // otherwise the last partial is missing in the reducer and the IndexedDB
    // history diverges from the server mirror. parseSseBlock is defensive
    // (skips broken frames), so a partial flush here is safe.
    if (buffer.trim()) {
      for (const event of parseSseBlock(buffer)) {
        opts.onEvent(event)
      }
    }
    await reader.cancel().catch(() => {})
    if (opts.signal?.aborted) {
      // Producer abort (stop button): not an error, resolves cleanly.
      return
    }
    if (err instanceof Error && err.name === 'AbortError') {
      return
    }
    throw new StreamChatError('Streamabbruch vor dem done-Event')
  }
}

/**
 * Parse one block (everything up to the next "\n\n") into events.
 * - lines starting with ":" = SSE comment/keep-alive → ignore
 * - several "data:" lines = one logical frame (concatenated) — here the
 *   backend always uses exactly one, but we stay spec-compliant
 * - invalid JSON → skip the frame (defensive, no crash)
 */
function parseSseBlock(block: string): StreamEvent[] {
  const lines = block.split(/\r?\n/)
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith(':')) continue // SSE comment (keep-alive)
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
    // event:/id:/retry: lines are unused → ignore
  }
  if (dataLines.length === 0) return []
  const payload = dataLines.join('\n')
  try {
    return [JSON.parse(payload) as StreamEvent]
  } catch {
    // Broken frame (e.g. incomplete JSON on stream abort) → skip
    return []
  }
}
