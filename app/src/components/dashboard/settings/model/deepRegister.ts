/**
 * I3-V5: where a tab field meets the user, and which sections a range shows.
 * Pure mapping — that is why it lives here and not inside the component.
 */
import type { DeepSection } from '@/types'
import type { TabKey } from '../types'

/** Where a tab field meets the user — search jumps to it. */
export const SECTION_TAB: Record<string, TabKey> = {
  // I6-3: the chat fields are behaviour, not appearance — they moved out of
  // appearance into the new range.
  chat: 'behaviour',
  appearance: 'appearance',
  // The desktop's one saveable shortcut; the rest of that area stays a read board.
  shortcuts: 'shortcuts',
  advanced: 'engine',
  plugins: 'plugins',
  // I6-7: the memory fields live in their own range — without this line
  // a search hit jumped to a place where the field is never visible.
  memory: 'memory',
  // R1 (WP7): ephemerality has its own range, because its control
  // has no effect inside a foreign range.
  ephemera: 'ephemera',
  cron: 'cron',
  hooks: 'hooks',
}

/** The sections a tab shows, in schema order — the nav's second level reads
 *  this instead of carrying a list of its own, so a new section appears in the
 *  column the moment SECTION_TAB names its tab. */
export function sectionsOfTab(sections: DeepSection[] | null, tab: TabKey): DeepSection[] {
  return (sections ?? []).filter((sec) => SECTION_TAB[sec.key] === tab)
}

export function deepFieldsOf(sections: DeepSection[] | null, prefixes: string[]) {
  return (sections ?? []).filter((sec) => prefixes.some((p) => sec.key === p.replace(/\.$/, '')))
}
