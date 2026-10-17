/**
 * I3-V5: the settings nav search — pure logic, so it is testable without mounting
 * the whole panel. It finds sections and individual settings, and says where a hit
 * leads.
 */
import { SECTION_TAB } from './deepRegister'
import { ROW_INDEX } from './rowIndex'
import type { DeepSection } from '@/types'
import type { TabKey } from '../types'

export interface FieldHit {
  secKey: string
  label: string
  tab: TabKey
}

export interface RowHit {
  tab: TabKey
  label: string
}

export function matchTabs<T extends { key: string }>(
  nav: readonly T[],
  labelOf: (entry: T) => string,
  query: string,
): T[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  return nav.filter((entry) => labelOf(entry).toLowerCase().includes(q))
}

export function matchFields(
  sections: DeepSection[] | null,
  query: string,
  isDe: boolean,
): FieldHit[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const hits: FieldHit[] = []
  for (const sec of sections ?? []) {
    // I7-5: no target section, no hit. The old fallback to 'appearance' led the
    // user into a section where the field never lives.
    const tab = SECTION_TAB[sec.key]
    if (!tab) continue
    for (const f of sec.fields) {
      const haystack = [f.label, f.labelEn, f.hint, f.hintEn, f.key].join('\n').toLowerCase()
      if (!haystack.includes(q)) continue
      hits.push({
        secKey: sec.key,
        label: (isDe ? f.label : f.labelEn || f.label) || f.label,
        tab,
      })
    }
  }
  return hits
}

/**
 * I7-5: everything that is not in the register — rows with their own endpoint.
 * The search runs over both languages, so an English word still finds its row in
 * the German interface (the user knows the terms from the docs).
 */
export function matchRows(
  translate: (key: string, opts?: Record<string, unknown>) => string,
  query: string,
): RowHit[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const hits: RowHit[] = []
  for (const entry of ROW_INDEX) {
    const de = translate(entry.key, { lng: 'de', defaultValue: '' })
    const en = translate(entry.key, { lng: 'en', defaultValue: '' })
    if (![de, en, entry.key].join('\n').toLowerCase().includes(q)) continue
    hits.push({ tab: entry.tab, label: translate(entry.key, { defaultValue: entry.key }) })
  }
  return hits
}
