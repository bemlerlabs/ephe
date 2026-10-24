/**
 * API client for Ephe — talks to the local backend.
 *
 * Default: same-origin. The PWA is served by the API server itself
 * (prod/one-command install) and, in dev, through the Vite proxy (5173 → 8765).
 * VITE_API_URL overrides this for external setups (e.g. a fixed remote port).
 * In the Tauri shell (tauri://localhost) the base URL points at the local
 * product server — see lib/desktopBaseUrl.ts.
 */
import { DESKTOP_BASE_URL as BASE_URL } from '../desktopBaseUrl'
export { BASE_URL }

// Re-export the types from the canonical source (types/index.ts) — single source of truth.
import type {
  ApiChatMessage as ChatMessage,
  ApiMessage as Message,
  ApiSession as Session,
  AppSettings,
  GenerationBlock,
  DeepSection,
  DeepField,
  ProviderSettings,
  ProviderType,
} from '@/types'

export type {
  AppSettings,
  GenerationBlock,
  DeepSection,
  DeepField,
  ProviderSettings,
  ProviderType,
  Session,
  Message,
  ChatMessage,
}

/**
 * LAN auth token: embedded in the URL as `?token=…` during the QR scan
 * (server/routes/mobile.py). In `--lan` mode the middleware protects every
 * /api/* call with X-Auth-Token; no token in the header → 401.
 * Desktop without ?token → no header (behaviour unchanged).
 */
export let LAN_TOKEN: string | null = null
if (typeof window !== 'undefined' && window.location.search) {
  const fromUrl = new URLSearchParams(window.location.search).get('token')
  if (fromUrl) {
    LAN_TOKEN = fromUrl
    // Take the token out of the address bar once (it does not stay in the tab)
    try {
      window.history.replaceState({}, '', window.location.pathname)
    } catch {
      /* file:// / sandbox without history — the token stays in the URL and still works */
    }
  }
}

/**
 * P2-1: URL for a generated artifact via /api/file. Media elements
 * (img/iframe) cannot send headers → in LAN mode the token travels as a query.
 */
export function fileUrl(path: string): string {
  const u = `${BASE_URL}/api/file?path=${encodeURIComponent(path)}`
  return LAN_TOKEN ? `${u}&token=${encodeURIComponent(LAN_TOKEN)}` : u
}

/**
 * W1-R3: a raw fetch() on an API path needs the same base as `request()` — in
 * the installed shell the origin is `tauri://localhost`, and a relative
 * `/api/...` runs into the asset handler there and never reaches the backend.
 * (On that path the update button was always `failed`.)
 */
export function apiUrl(path: string): string {
  const u = `${BASE_URL}${path}`
  return LAN_TOKEN ? `${u}${u.includes('?') ? '&' : '?'}token=${encodeURIComponent(LAN_TOKEN)}` : u
}

/**
 * P1-5: WebSocket URL for the same backend. BASE_URL is '' in the browser
 * (same-origin) and `http://127.0.0.1:8765` in the Tauri shell — both become
 * ws/wss. Browser WebSockets cannot send headers, so in LAN mode the auth
 * token travels as a query (ws_client_authorized reads it there).
 */
export function wsUrl(path: string): string {
  const origin =
    BASE_URL ||
    (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.host}` : '')
  const wsBase = origin.replace(/^http/, 'ws')
  const u = `${wsBase}${path}`
  return LAN_TOKEN ? `${u}${u.includes('?') ? '&' : '?'}token=${encodeURIComponent(LAN_TOKEN)}` : u
}

export class ApiError extends Error {
  /** Status code of the server — surfaces that have to answer 409/422 differently
   * than 500 need more than the message. */
  readonly status: number
  /** The refusal's own name, when the server sent one: stable across languages, so a
   * surface can branch on it instead of matching the text it shows. */
  readonly reasonCode: string
  /** The full `error.detail` body, when the server sent one (a 428 delta, a refusal). */
  readonly payload: unknown
  constructor(message: string, status: number, reasonCode = '', payload: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.reasonCode = reasonCode
    this.payload = payload
  }
}

/**
 * R36: a bound the caller can name per call, next to the register's own.
 *
 * `request()` waits at most `advanced.api_timeout` — the field the register
 * documents as "one non-streaming request" (default 120 s, core/settings_schema.py).
 * Every caller on this path fits inside that: the longest server-side budget
 * among them is the 90 s synthesis cap in server/routes/audio.py. A caller that
 * ever needs more names its own `timeoutMs`; 0 turns the bound off.
 */
export interface RequestOptions extends RequestInit {
  timeoutMs?: number
}

/** Register fallback, equal to the field's own default. */
const API_TIMEOUT_DEFAULT_S = 120

/**
 * The bound in ms, read at the point of use — the same rule the chat stream
 * follows for `chat.stream_idle_seconds`, so a save in the settings panel takes
 * effect without a reload. A missing register leaves the default.
 */
async function requestBoundMs(): Promise<number> {
  try {
    const { deepNumber } = await import('../deepSettings')
    return Math.max(0, deepNumber('advanced.api_timeout', API_TIMEOUT_DEFAULT_S)) * 1000
  } catch {
    return API_TIMEOUT_DEFAULT_S * 1000
  }
}

export async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { timeoutMs, signal: callerSignal, headers: callerHeaders, ...rest } = init ?? {}
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    // W16: XHR marker — the shell route uses it to recognise the PWA's own calls
    // (CSRF guard against simple cross-origin form POSTs).
    'X-Requested-With': 'XMLHttpRequest',
  }
  if (callerHeaders) {
    new Headers(callerHeaders as HeadersInit).forEach((value, key) => {
      headers[key] = value
    })
  }
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN

  // R36: a backend that accepts the connection and then never answers left
  // `fetch` pending forever — no status, no rejection — and the first paint
  // waits on exactly such a call (GET /api/setup/status). The bound ends that
  // wait with a coded error instead. The chat stream does not come through
  // here: lib/stream.ts keeps its own idle bound (chat.stream_idle_seconds).
  const boundMs = timeoutMs ?? (await requestBoundMs())
  const controller = new AbortController()
  let timedOut = false
  // One controller carries both: the caller's own signal (a new keystroke
  // cancels the session search) and the bound. Either one aborts the fetch.
  const forward = () => controller.abort(callerSignal?.reason)
  if (callerSignal) {
    if (callerSignal.aborted) forward()
    else callerSignal.addEventListener('abort', forward, { once: true })
  }
  const timer =
    boundMs > 0
      ? setTimeout(() => {
          timedOut = true
          controller.abort()
        }, boundMs)
      : null

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers,
      ...rest,
      signal: controller.signal,
    })
    if (!res.ok) {
      // Pass the backend error detail through (middleware shape: {error:{message}}). A refusal
      // that names its reason is answered from the bundle instead, so the reader gets the
      // sentence in the language they set; the server's own text stays the fallback.
      let detail = `API ${res.status}: ${res.statusText}`
      let reasonCode = ''
      let payload: unknown = null
      try {
        const body = (await res.json()) as {
          error?: {
            message?: string
            reason_code?: string
            reason_params?: Record<string, string | number>
            detail?: { code?: string }
          }
          detail?: string
        }
        const code = body.error?.reason_code ?? body.error?.detail?.code ?? ''
        reasonCode = code
        payload = body.error?.detail ?? body.detail ?? null
        // Loaded here rather than at the top: the i18n instance initialises react-i18next, and
        // a module-level import would pull that into every file that mocks it.
        const { serverErrorText } = await import('../serverError')
        detail =
          serverErrorText(code, body.error?.reason_params) ||
          body.error?.message ||
          body.detail ||
          detail
      } catch {
        /* Body is not JSON → generic message */
      }
      throw new ApiError(detail, res.status, reasonCode, payload)
    }
    return res.json() as Promise<T>
  } catch (err) {
    // The bound fired: report it as the coded refusal it is, on the same ApiError
    // the HTTP failures use, so every existing catch/toast surface reads it.
    if (!timedOut) throw err
    const { serverErrorText } = await import('../serverError')
    throw new ApiError(
      serverErrorText(
        'request_timeout',
        undefined,
        'The backend did not answer in time — check that Ephe is running, then try again.',
      ),
      408,
      'request_timeout',
    )
  } finally {
    if (timer !== null) clearTimeout(timer)
    callerSignal?.removeEventListener('abort', forward)
  }
}
