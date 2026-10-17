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

export function deepFieldsOf(sections: DeepSection[] | null, prefixes: string[]) {
  return (sections ?? []).filter((sec) => prefixes.some((p) => sec.key === p.replace(/\.$/, '')))
}
