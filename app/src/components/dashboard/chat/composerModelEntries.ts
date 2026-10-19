/**
 * Ephe — composer model entries (P3 wave 2026-10-05, split out of ChatInput: the
 * composer file sits far above the architecture limit).
 *
 * N9 — fallback schema at the model chip: when GET /api/model/providers returns no
 * units (first start without engine.json, empty provider table), the environment
 * scan findings are merged in as options. Deduplication runs over the scrubbed
 * triple (provider kind, scrubbed endpoint, model name); the mirror's
 * ``preferred`` row (its reference harness) sorts first.
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
import { derivePick, scrubUrl } from '../../shell/EnvironmentTools'
import type { MirrorTool } from '@/lib/api/environment'
import {
  hasUnfilledTemplate,
  isJunkModel,
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

/** The chip row leads with the tool's own name as the mirror reports it, first
 *  letter up — a display transform of data, so no product name is spelled here. */
export function displayToolName(tool: string): string {
  return tool ? tool.charAt(0).toUpperCase() + tool.slice(1) : tool
}

export function buildScanEntries(tools: MirrorTool[]): ModelChipEntry[] {
  const out: ModelChipEntry[] = []
  const seen = new Set<string>()
  for (const tool of [...tools]
    .filter((t) => t.installed)
    .sort((a, b) => Number(Boolean(b.preferred)) - Number(Boolean(a.preferred)))) {
    for (const model of tool.models) {
      // F-J: do not offer embedding/test models from the scan.
      if (isJunkModel(model)) continue
      const pick = derivePick(tool, model)
      if (!pick) continue
      const ep = pick.endpoint ? scrubUrl(pick.endpoint) : ''
      const dedupe = `${pick.providerKind}|${ep}|${pick.model}`
      if (seen.has(dedupe)) continue
      seen.add(dedupe)
      // Only the mirror's own free list says a model is free. A `-free` / `:free`
      // suffix is another service's naming convention, not a fact about this endpoint.
      const isFree = (tool.free_models ?? []).includes(model)
      out.push({
        id: `${tool.tool}:${model}`,
        kind: pick.providerKind,
        model: pick.model,
        endpoint: ep || undefined,
        endpointKind: endpointKindOf(ep),
        free: isFree || undefined,
        unconfigured: hasUnfilledTemplate(ep) || undefined,
        label: `${displayToolName(tool.tool)} · ${pick.model}`,
      })
    }
  }
  return out
}

/** B8: scan findings supplement the preset units — deduplicated over (identifier,
 *  model); earlier entries (presets) win. Key is 'kind' for scan entries,
 *  'provider'/'id' for presets. */
export function mergeScanEntries(base: ModelChipEntry[], scan: ModelChipEntry[]): ModelChipEntry[] {
  const seen = new Set(base.map((p) => `${p.kind ?? p.provider ?? p.id ?? ''}|${p.model ?? ''}`))
  const extra = scan.filter((e) => {
    const key = `${e.kind ?? e.id ?? ''}|${e.model ?? ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  return [...base, ...extra]
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
