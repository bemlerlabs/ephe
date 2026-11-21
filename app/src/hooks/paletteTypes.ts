/** Shared result type of the command palette (cycle-free between hook and item builders). */
import type { ShortcutId } from '@/lib/shortcuts'

export interface CommandItem {
  id: string
  label: string
  section: string
  action: () => void
  /** P1-16: the row in `lib/shortcuts.ts` that drives this command's key. The
   *  palette no longer carries its own key strings — before this it rendered a
   *  hand-written `⌘K` on an entry that did not even open the palette. Commands
   *  with no key leave this empty; that is the honest statement, not a bug. */
  shortcutId?: ShortcutId
  icon?: string
  hint?: string
}
