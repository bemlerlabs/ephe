/**
 * S2 — the row shape one model picker speaks, whatever host mounts it.
 *
 * Three surfaces list models (setup, the engine settings, the composer chip) and each
 * used to render its own record from its own endpoint. This is the one shape they all
 * reduce to: an id, the display name only when the endpoint supplied one, a group label
 * for the heading, and the nullable metadata S1 emits. An unknown stays null and reads
 * as an em-dash; a row never carries a number the product guessed.
 */
import type { DetectedEngine, ModelMetadata, ModelOption } from '@/lib/api'
import { entryKey, isUnconfiguredEntry } from '@/components/dashboard/chat/composerModelEntries'
import type { EndpointKind, ModelChipEntry } from '@/components/dashboard/chat/composerModelEntries'

/** What a column prints where the engine said nothing. A glyph, so no locale holds it. */
export const UNKNOWN_CELL = '—'

/** The nullable per-model facts. `null` means the engine did not say. */
export interface ModelMeta {
  contextWindow: number | null
  priceInPerM: number | null
  priceOutPerM: number | null
  isFree: boolean | null
  supportsTools: boolean | null
  supportsVision: boolean | null
}

export const UNKNOWN_META: ModelMeta = {
  contextWindow: null,
  priceInPerM: null,
  priceOutPerM: null,
  isFree: null,
  supportsTools: null,
  supportsVision: null,
}

export interface ModelRow {
  /** Stable identity for keys, favorites and recents. */
  key: string
  /** The tag a request sends. Never a display name. */
  id: string
  displayName: string | null
  /** Heading the row sits under — display only, never written back. */
  group: string
  endpoint?: string
  endpointKind?: EndpointKind
  /** What a host wants shown beside the title instead of the raw endpoint — the
   *  composer prints `local` / `private network` / `not configured`, never a URL. */
  hint?: string
  /** An endpoint template with an unfilled variable cannot be chosen. */
  selectable: boolean
  meta: ModelMeta
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

/** The wire's nullable record, read without inventing a default. */
export function metaFrom(record: ModelMetadata | undefined | null): ModelMeta {
  if (!record) return { ...UNKNOWN_META }
  return {
    contextWindow: asNumber(record.context_window),
    priceInPerM: asNumber(record.price_in_per_m),
    priceOutPerM: asNumber(record.price_out_per_m),
    isFree: asBoolean(record.is_free),
    supportsTools: asBoolean(record.supports_tools),
    supportsVision: asBoolean(record.supports_vision),
  }
}

/** The provider half of an id a service namespaces (`vendor/model`). */
export function vendorPrefix(id: string): string | null {
  const cut = id.indexOf('/')
  if (cut <= 0 || cut === id.length - 1) return null
  return id.slice(0, cut)
}

function baseRow(fields: {
  id: string
  displayName?: string | null
  group: string
  endpoint?: string
  endpointKind?: EndpointKind
  selectable?: boolean
  meta: ModelMeta
}): ModelRow {
  const { id, displayName = null, group, endpoint, endpointKind, selectable = true, meta } = fields
  return {
    key: `${group}|${endpoint ?? ''}|${id}`,
    id,
    displayName: displayName || null,
    group,
    endpoint,
    endpointKind,
    selectable,
    meta,
  }
}

/** Probe answer: aligned `models` + `model_details`, the richest source there is. */
export function rowsFromProbe(
  models: string[],
  details: ModelMetadata[] | undefined,
  group: string,
): ModelRow[] {
  const byId = new Map((details ?? []).map((d) => [d.id, d]))
  return models.map((id) =>
    baseRow({ id, group, meta: metaFrom(byId.get(id)), displayName: byId.get(id)?.name ?? null }),
  )
}

/** Engine settings list: Ollama options and OpenAI-compatible ids carry the same keys. */
export function rowsFromOptions(options: ModelOption[], group: string): ModelRow[] {
  return options.map((option) => {
    const id = option.model ?? option.name
    return baseRow({
      id,
      group,
      displayName: option.label && option.label !== id ? option.label : null,
      meta: metaFrom(option),
    })
  })
}

/** What a scan found: a name and an endpoint, and no metadata at all — unknown, not free. */
export function rowsFromDetected(engine: DetectedEngine, group: string): ModelRow[] {
  const byId = new Map((engine.model_details ?? []).map((d) => [d.id, d]))
  return (engine.models ?? []).map((id) =>
    baseRow({
      id,
      group,
      endpoint: engine.url ?? undefined,
      meta: metaFrom(byId.get(id)),
      displayName: byId.get(id)?.name ?? null,
    }),
  )
}

/** The composer's chip entries, reduced to the picker's row.
 *
 *  A scan finding carries a name, a kind and an endpoint, and no metadata at all, so
 *  every capability stays null and the row prints em-dashes. The section label comes
 *  from the host's own taxonomy; `hint` is the endpoint as the row may print it. */
export function rowsFromEntries(
  entries: ModelChipEntry[],
  group: string,
  hintOf?: (entry: ModelChipEntry) => string,
): ModelRow[] {
  return entries.map((entry) => {
    const key = entryKey(entry)
    return {
      ...baseRow({
        id: entry.model ?? key,
        displayName: entry.label,
        group,
        endpoint: entry.endpoint,
        endpointKind: entry.endpointKind,
        selectable: !isUnconfiguredEntry(entry),
        meta: {
          contextWindow: entry.context_window ?? null,
          priceInPerM: entry.price_in_per_m ?? null,
          priceOutPerM: entry.price_out_per_m ?? null,
          isFree: entry.is_free ?? entry.free ?? null,
          supportsTools: entry.supports_tools ?? null,
          supportsVision: entry.supports_vision ?? null,
        },
      }),
      hint: hintOf?.(entry) || undefined,
    }
  })
}
