/**
 * N8 — the dock icon carries the run the window shows.
 *
 * A badge while a turn streams (`2/5` when the plan has steps, a dot when it
 * does not) and a progress bar from the same plan; idle clears both fields.
 * Only the shell has a dock, so a browser returns before it asks.
 */
import { tauriInvoke } from './tauriBridge'

export interface DockRun {
  busy: boolean
  done: number
  total: number
}

export async function syncDockStatus(run: DockRun): Promise<void> {
  const invoke = tauriInvoke()
  if (!invoke) return
  const badge = !run.busy ? '' : run.total > 0 ? `${run.done}/${run.total}` : '●'
  const percent = run.busy && run.total > 0 ? Math.min(100, (run.done / run.total) * 100) : null
  try {
    await invoke('set_dock_badge', { badge })
    await invoke('set_dock_progress', { percent })
  } catch {
    // An older shell, or a platform without a dock: nothing to paint.
  }
}
