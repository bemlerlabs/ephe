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

/** The readiness the shell recorded, or null outside the shell. */
export async function readBackendReadiness(): Promise<BackendReadiness | null> {
  const invoke = tauriInvoke()
  if (!invoke) return null
  try {
    const raw = (await invoke('backend_readiness')) as Record<string, unknown> | null
    if (!raw) return null
    return {
      ready: raw.bereit === true,
      state: String(raw.state ?? 'unknown'),
      port: Number(raw.port ?? 8765),
      baseUrl: String(raw.base_url ?? ''),
      config: String(raw.config ?? ''),
      sentence: String(raw.sentence ?? ''),
      action: String(raw.action ?? ''),
    }
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
      next({
        ready: raw.bereit === true,
        state: String(raw.state ?? 'unknown'),
        port: Number(raw.port ?? 8765),
        baseUrl: String(raw.base_url ?? ''),
        config: String(raw.config ?? ''),
        sentence: String(raw.sentence ?? ''),
        action: String(raw.action ?? ''),
      })
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
