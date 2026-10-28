/**
 * Ephe — the single entry point into the shell (R4).
 *
 * `@tauri-apps/api` is not a dependency of this project: the globally injected
 * bridge (`withGlobalTauri`) is the only way in. Before this module every bridge
 * helper copied its own access code — and exactly once that lookup was forgotten
 * (the update button never worked inside the shell). One access, one question:
 * is the bridge there?
 */
type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>

export function tauriInvoke(): Invoke | null {
  if (typeof window === 'undefined') return null
  const core = (window as unknown as { __TAURI__?: { core?: { invoke?: unknown } } }).__TAURI__
    ?.core?.invoke
  return typeof core === 'function' ? (core as Invoke) : null
}

/** The shell itself — not a browser tab that merely happens to run locally. */
export function isDesktopShell(): boolean {
  return tauriInvoke() !== null
}

/** Whether the shell window is fullscreen, or null where the bridge cannot say. */
export async function windowIsFullscreen(): Promise<boolean | null> {
  if (typeof window === 'undefined') return null
  const api = (
    window as unknown as {
      __TAURI__?: { window?: { getCurrentWindow?: () => { isFullscreen?: () => Promise<boolean> } } }
    }
  ).__TAURI__?.window
  try {
    const current = api?.getCurrentWindow?.()
    if (!current?.isFullscreen) return null
    return await current.isFullscreen()
  } catch {
    return null
  }
}
