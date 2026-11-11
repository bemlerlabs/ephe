/**
 * The shell's own answer about the backend it starts (issues #193/#194).
 *
 * An installed window starts a backend only when `~/.ephe/desktop.json` names one. It used to
 * answer "Ready" with a live composer while nothing ran, because the surface had no way to ask.
 * The shell records one readiness value and emits `ephe:backend-state`; this module reads it and
 * says nothing of its own — a browser tab has a server by definition, so it is ready.
 */
import { isDesktopShell, tauriInvoke } from './tauriBridge'

export type BackendReadiness = {
  /** Whether a backend this window can talk to is serving. */
  ready: boolean
  /** `serving`, `started`, `unconfigured`, `port_mismatch`, `start_failed`, `unsupported`. */
  state: string
  port: number
  baseUrl: string
  /** The desktop.json this window read, when one exists. */
  config: string
  /** One sentence naming the state, and the one action that would change it. */
  sentence: string
  action: string
}

const EVENT = 'ephe:backend-state'

/** One parser for the shell's answer, used by the read and the event. */
function parseReadiness(raw: Record<string, unknown>): BackendReadiness {
  return {
    // The shell serialises `Readiness` with its own field names (`ready`); older
    // surfaces read `bereit` and never saw a true value, which left the composer
    // disabled for the whole window. Read the contract, and accept the old spelling
    // so a mixed pair cannot lock the composer again.
    ready: raw.ready === true || raw.bereit === true,
    state: String(raw.state ?? 'unknown'),
    port: Number(raw.port ?? 8765),
    baseUrl: String(raw.base_url ?? ''),
    config: String(raw.config ?? ''),
    sentence: String(raw.sentence ?? ''),
    action: String(raw.action ?? ''),
  }
}

/** The readiness the shell recorded, or null outside the shell. */
export async function readBackendReadiness(): Promise<BackendReadiness | null> {
  const invoke = tauriInvoke()
  if (!invoke) return null
  try {
    const raw = (await invoke('backend_readiness')) as Record<string, unknown> | null
    if (!raw) return null
    return parseReadiness(raw)
  } catch {
    return null
  }
}

type TauriEventBridge = {
  listen: (name: string, cb: (event: { payload?: unknown }) => void) => Promise<() => void>
}

/** Subscribe to the shell's state changes; returns the unsubscribe.
 *
 * The channel is `window.__TAURI__.event`, the same one the update flow uses — @tauri-apps/api is
 * not a dependency of this project. */
export function onBackendReadiness(next: (value: BackendReadiness) => void): () => void {
  const ev = (window as { __TAURI__?: { event?: TauriEventBridge } }).__TAURI__?.event
  if (!ev?.listen || !isDesktopShell()) return () => {}
  let unlisten: (() => void) | undefined
  let dead = false
  void ev
    .listen(EVENT, (event) => {
      const raw = (event?.payload ?? {}) as Record<string, unknown>
      next(parseReadiness(raw))
    })
    .then((fn) => {
      if (dead) fn()
      else unlisten = fn
    })
  return () => {
    dead = true
    unlisten?.()
  }
}

/** States in which a message cannot leave this window at all.
 *
 * `starting` is deliberately absent: the shell just began the backend and it answers
 * after a few seconds, so a composer that refuses keys for that window is a dead
 * composer for no reason. A send that loses the race fails with the surface's own
 * error, which is a sentence a person can read.
 */
const DEAD_STATES = new Set([
  'unconfigured',
  'refused',
  'unreachable',
  'unsupported',
  'port_mismatch',
  'start_failed',
])

/** Whether the composer belongs to a window that can send anything. */
export function composerBlocked(readiness: BackendReadiness | null): boolean {
  if (!readiness || readiness.ready) return false
  return DEAD_STATES.has(readiness.state)
}
