// I3-3: range SSOT — the bounds come from the payload, the client clamps first.
//
// The limits used to stand as text in the TSX ('0–2', '1–40') while
// core/engine_config.py::GENERATION_BOUNDS and core/settings_schema.py held the
// truth. The client sent raw values and the user saw the consequence only as a
// 422 toast. This is the one mechanical place for both slider surfaces.

import type { DeepSection } from '@/types'

export interface NumBound {
  min?: number
  max?: number | null
}

/** Clamp a number to its bound; non-finite values stay untouched. */
export function clampToBound(value: number, bound: NumBound | undefined): number {
  if (!Number.isFinite(value) || !bound) return value
  let out = value
  if (typeof bound.min === 'number') out = Math.max(bound.min, out)
  if (typeof bound.max === 'number') out = Math.min(bound.max, out)
  return out
}

/** Display text built from the bounds — '0–2' is no longer typed in. */
export function rangeLabel(bound: NumBound | undefined): string {
  if (!bound || typeof bound.min !== 'number') return ''
  return typeof bound.max === 'number' ? `${bound.min}–${bound.max}` : `≥${bound.min}`
}

/**
 * Build the generation block from the draft: empty = unset (the server default
 * is kept), a number = clamped to its bound. `bounds` is missing against a
 * backend before I3-3 — then the raw value passes through, just as before.
 */
export function generationValues(
  draft: Record<string, string>,
  keys: readonly string[],
  bounds: Record<string, NumBound> | undefined,
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const key of keys) {
    const raw = draft[key]?.trim()
    if (raw === undefined || raw === '') continue
    const num = Number(raw)
    if (Number.isNaN(num)) continue
    out[key] = clampToBound(num, bounds?.[key])
  }
  return out
}

/**
 * Clamp the expert register before sending: number fields only, finite values
 * only. An empty field stays empty (unset); bool/select/text stay untouched.
 */
export function clampDeepDraft(
  draft: Record<string, Record<string, string | number | boolean>>,
  sections: DeepSection[] | null,
): Record<string, Record<string, string | number | boolean>> {
  if (!sections) return draft
  const bounds = new Map<string, NumBound>()
  for (const sec of sections) {
    for (const f of sec.fields) {
      if (f.type === 'number') bounds.set(f.key, { min: f.min, max: f.max })
    }
  }
  const next: Record<string, Record<string, string | number | boolean>> = {}
  for (const [secKey, fields] of Object.entries(draft)) {
    const cleaned: Record<string, string | number | boolean> = {}
    for (const [fieldKey, value] of Object.entries(fields)) {
      cleaned[fieldKey] =
        typeof value === 'number' ? clampToBound(value, bounds.get(fieldKey)) : value
    }
    next[secKey] = cleaned
  }
  return next
}

/**
 * I6-1: the footer button's counter. A draft value counts as a change when it is
 * set and differs from the register value — the same measure the register's own
 * button used to apply. It also decides whether settings.json is written
 * at all: no change, no write.
 */
export function countDeepChanges(
  sections: DeepSection[] | null,
  draft: Record<string, Record<string, string | number | boolean>>,
): number {
  let changed = 0
  for (const sec of sections ?? []) {
    const cur = draft[sec.key] ?? {}
    for (const f of sec.fields) {
      const value = cur[f.key]
      if (value === undefined || value === '') continue
      if (value !== (f.value ?? f.default ?? '')) changed += 1
    }
  }
  return changed
}
