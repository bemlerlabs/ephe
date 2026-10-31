/**
 * Ephe — composer model entries (P3 wave 2026-10-05, split out of ChatInput: the
 * composer file sits far above the architecture limit).
 *
 * The list is the provider table's: the chip does not read another application's
 * config files to fill itself, so an empty table stays empty until this app has
 * been given an engine.
 *
 * P3 — hygiene over the list:
 *  · endpoint templates with an unfilled variable (`${SNOWFLAKE_ACCOUNT}`) are not
 *    usable → the entry stays visible but `unconfigured` (never selectable).
 *  · loopback/private endpoints do not appear as raw URLs in the list; their real
 *    value is kept in `endpoint` (request + tooltip).
 *  · speech/image models are separated by type (`groupModelEntries`).
 *
 * Everything here is a pure transformation of real data — nothing is invented.
 */
import {
  hasUnfilledTemplate,
  isLoopbackEndpoint,
  isPrivateEndpoint,
  modelKind,
} from '@/lib/modelFilter'

/** Section in the chip menu. */
export type ModelGroup = 'chat' | 'other' | 'unconfigured'

/**
 * How a row's endpoint becomes visible. The real value always stays in `endpoint`
 * (PUT + tooltip) — only the display is sorted: raw loopback/Tailnet URLs do not
 * belong in a picker list.
 */
export type EndpointKind = 'none' | 'loopback' | 'private' | 'url'

export function endpointKindOf(endpoint?: string): EndpointKind {
  if (!endpoint) return 'none'
  if (isLoopbackEndpoint(endpoint)) return 'loopback'
  if (isPrivateEndpoint(endpoint)) return 'private'
  return 'url'
}

export interface ModelChipEntry {
  id?: string
  provider?: string
  model?: string
  label: string
  /** Provider identifier for setModelProvider (scan entries: derived). */
  kind?: string
  /** Derived API endpoint of the scan finding (scrubbed) — absent for presets;
   *  scan picks need it, otherwise the model ends up talking to the wrong engine. */
  endpoint?: string
  /** P3: how the endpoint is displayed in the list. */
  endpointKind?: EndpointKind
  /** Free model (no subscription needed) — derived from free_models. */
  free?: boolean
  /** S2: what the provider table said about this model, when it names it. Null is
   *  "not stated" and reads as unknown in the picker; the mirror's `free` is a fact
   *  of its own and stays the fallback only where no metadata exists. */
  context_window?: number | null
  price_in_per_m?: number | null
  price_out_per_m?: number | null
  is_free?: boolean | null
  supports_tools?: boolean | null
  supports_vision?: boolean | null
  /** P3: the endpoint is an unfilled template → the row shows "not configured"
   *  and is not selectable. */
  unconfigured?: boolean
}

/** The row is not selectable because its endpoint carries an unfilled template. */
export function isUnconfiguredEntry(entry: ModelChipEntry): boolean {
  return Boolean(entry.unconfigured) || hasUnfilledTemplate(entry.endpoint)
}

/** Key of a row — stable for data-testid (K3 Z24 pins on it). */
export function entryKey(p: ModelChipEntry): string {
  return p.provider ?? p.id ?? p.label
}

/** Is this the currently active row? (provider identifier or model name) */
export function isActiveEntry(p: ModelChipEntry, activeP: string, model: string): boolean {
  const key = entryKey(p)
  return key === activeP || (activeP === '' && (p.model === model || p.label === model))
}

/**
 * Sections: the unselectable template findings on their own (so nobody mistakes
 * them for selectable), then chat models, then other model types. The order inside
 * each section stays the delivery order.
 */
export function groupModelEntries(entries: ModelChipEntry[]): Record<ModelGroup, ModelChipEntry[]> {
  const groups: Record<ModelGroup, ModelChipEntry[]> = { chat: [], other: [], unconfigured: [] }
  for (const e of entries) {
    if (isUnconfiguredEntry(e)) groups.unconfigured.push(e)
    else if (modelKind(e.model ?? e.id) !== 'chat') groups.other.push(e)
    else groups.chat.push(e)
  }
  return groups
}

/** Search text of a row: label + model + identifier + endpoint (lowercase, no blanks). */
export function entrySearchText(e: ModelChipEntry): string {
  return [e.label, e.model, e.id, e.provider, e.kind, e.endpoint]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

/** From the first character on: every space-separated word has to hit. */
export function entryMatchesQuery(e: ModelChipEntry, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = entrySearchText(e)
  return q.split(/\s+/).every((token) => hay.includes(token))
}
