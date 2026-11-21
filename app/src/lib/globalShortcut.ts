/**
 * The desktop's one opt-in global chord. The shell owns registration; this
 * module only carries the request and reports what happened. A browser tab has
 * no window manager to claim a key from, so `unsupported` is a real answer.
 */
import { tauriInvoke } from './tauriBridge'

export type ShortcutOutcome = 'applied' | 'disabled' | 'unsupported' | 'failed'

export const GLOBAL_SHORTCUT_KEYS = ['mod', 'shift', 'e'] as const

export async function ensureGlobalShortcut(enabled: boolean): Promise<ShortcutOutcome> {
  const invoke = tauriInvoke()
  if (!invoke) return 'unsupported'
  if (!enabled) {
    try {
      await invoke('set_global_shortcut', { enabled: false })
    } catch {
      // Disabling is best effort: a chord that was never registered has
      // nothing to release, and that is not a failure the user can act on.
    }
    return 'disabled'
  }
  try {
    await invoke('set_global_shortcut', { enabled: true })
    return 'applied'
  } catch {
    try {
      await invoke('set_global_shortcut', { enabled: false })
    } catch {
      // The failed registration is the report; cleanup stays silent.
    }
    return 'failed'
  }
}
