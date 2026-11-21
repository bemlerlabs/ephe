import type { DeepField } from '@/types'

export type AppearanceValue = string | number | boolean
export type AppearanceValues = Record<string, AppearanceValue>

export interface AppearanceProfile {
  ephe_appearance: 1
  values: AppearanceValues
}

export type ProfileReason =
  'bad_json' | 'bad_version' | 'unknown_key' | 'invalid_enum' | 'out_of_range'

export type ParseResult =
  { ok: true; values: AppearanceValues } | { ok: false; reason: ProfileReason }

/** The current appearance values, one object in the shipped profile shape. */
export function appearanceProfile(
  fields: DeepField[],
  draft: AppearanceValues | undefined,
): AppearanceProfile {
  const values: AppearanceValues = {}
  for (const field of fields) {
    values[field.key] = draft?.[field.key] ?? field.value ?? field.default ?? ''
  }
  return { ephe_appearance: 1, values }
}

/** Every appearance default — the Reset row writes exactly this. */
export function appearanceDefaults(fields: DeepField[]): AppearanceValues {
  const values: AppearanceValues = {}
  for (const field of fields) values[field.key] = field.default ?? ''
  return values
}

/**
 * Validate an appearance profile before one write. The version, keys, enum
 * choices and numeric bounds are checked; an out-of-range number is a refusal,
 * never a clamp, and no partial set is applied.
 */
export function parseAppearanceProfile(text: string, fields: DeepField[]): ParseResult {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return { ok: false, reason: 'bad_json' }
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ok: false, reason: 'bad_json' }
  }
  const body = raw as { ephe_appearance?: unknown; values?: unknown }
  if (body.ephe_appearance !== 1) return { ok: false, reason: 'bad_version' }
  if (!body.values || typeof body.values !== 'object' || Array.isArray(body.values)) {
    return { ok: false, reason: 'bad_json' }
  }
  const byKey = new Map(fields.map((field) => [field.key, field]))
  const values: AppearanceValues = {}
  for (const [key, value] of Object.entries(body.values as Record<string, unknown>)) {
    const field = byKey.get(key)
    if (!field) return { ok: false, reason: 'unknown_key' }
    if (field.type === 'number') {
      if (typeof value !== 'number' || !Number.isFinite(value)) {
        return { ok: false, reason: 'bad_json' }
      }
      if (
        (field.min !== undefined && value < field.min) ||
        (field.max !== undefined && value > field.max)
      ) {
        return { ok: false, reason: 'out_of_range' }
      }
      values[key] = value
    } else if (field.type === 'bool') {
      if (typeof value !== 'boolean') return { ok: false, reason: 'bad_json' }
      values[key] = value
    } else if (field.type === 'select') {
      if (typeof value !== 'string' || !(field.options ?? []).includes(value)) {
        return { ok: false, reason: 'invalid_enum' }
      }
      values[key] = value
    } else {
      if (typeof value !== 'string') return { ok: false, reason: 'bad_json' }
      values[key] = value
    }
  }
  return { ok: true, values }
}
