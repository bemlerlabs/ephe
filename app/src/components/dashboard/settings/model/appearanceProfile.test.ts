import { describe, expect, it } from 'vitest'
import type { DeepField } from '@/types'
import { appearanceDefaults, appearanceProfile, parseAppearanceProfile } from './appearanceProfile'

const FIELDS: DeepField[] = [
  {
    key: 'appearance.accent',
    type: 'select',
    label: 'Akzent',
    labelEn: 'Accent',
    default: 'ember',
    value: 'ember',
    options: ['ember', 'indigo', 'plum', 'mono'],
  },
  {
    key: 'appearance.font_scale',
    type: 'number',
    label: 'Schriftgröße (%)',
    labelEn: 'Font scale (%)',
    default: 100,
    value: 100,
    min: 80,
    max: 150,
  },
  {
    key: 'appearance.animations_enabled',
    type: 'bool',
    label: 'Animationen aktiv',
    labelEn: 'Animations enabled',
    default: true,
    value: true,
  },
]

const profile = (values: Record<string, unknown>, version = 1) =>
  JSON.stringify({ ephe_appearance: version, values })

describe('appearance profile', () => {
  it('builds the shipped shape from the current values', () => {
    const built = appearanceProfile(FIELDS, { 'appearance.accent': 'plum' })
    expect(built.ephe_appearance).toBe(1)
    expect(built.values).toEqual({
      'appearance.accent': 'plum',
      'appearance.font_scale': 100,
      'appearance.animations_enabled': true,
    })
  })

  it('resets to the register defaults, accent included', () => {
    expect(appearanceDefaults(FIELDS)).toEqual({
      'appearance.accent': 'ember',
      'appearance.font_scale': 100,
      'appearance.animations_enabled': true,
    })
  })

  it('accepts a complete and a partial valid profile', () => {
    expect(parseAppearanceProfile(profile({ 'appearance.accent': 'indigo' }), FIELDS)).toEqual({
      ok: true,
      values: { 'appearance.accent': 'indigo' },
    })
    expect(
      parseAppearanceProfile(
        profile({
          'appearance.accent': 'mono',
          'appearance.font_scale': 120,
          'appearance.animations_enabled': false,
        }),
        FIELDS,
      ),
    ).toEqual({
      ok: true,
      values: {
        'appearance.accent': 'mono',
        'appearance.font_scale': 120,
        'appearance.animations_enabled': false,
      },
    })
  })

  it('refuses malformed JSON and the wrong version', () => {
    expect(parseAppearanceProfile('{', FIELDS)).toEqual({ ok: false, reason: 'bad_json' })
    expect(parseAppearanceProfile(profile({}, 2), FIELDS)).toEqual({
      ok: false,
      reason: 'bad_version',
    })
  })

  it('refuses an unknown key before it writes anything', () => {
    expect(parseAppearanceProfile(profile({ 'appearance.skin': 'x' }), FIELDS)).toEqual({
      ok: false,
      reason: 'unknown_key',
    })
  })

  it('refuses a choice outside the curated enum', () => {
    expect(parseAppearanceProfile(profile({ 'appearance.accent': 'neon' }), FIELDS)).toEqual({
      ok: false,
      reason: 'invalid_enum',
    })
  })

  it('refuses a number outside the register bounds instead of clamping it', () => {
    expect(parseAppearanceProfile(profile({ 'appearance.font_scale': 999 }), FIELDS)).toEqual({
      ok: false,
      reason: 'out_of_range',
    })
  })

  it('refuses a value of the wrong type', () => {
    expect(parseAppearanceProfile(profile({ 'appearance.font_scale': '120' }), FIELDS)).toEqual({
      ok: false,
      reason: 'bad_json',
    })
    expect(
      parseAppearanceProfile(profile({ 'appearance.animations_enabled': 'yes' }), FIELDS),
    ).toEqual({ ok: false, reason: 'bad_json' })
  })
})
