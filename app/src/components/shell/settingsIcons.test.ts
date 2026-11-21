import { describe, expect, it } from 'vitest'
import {
  Brain,
  Cable,
  Coins,
  DatabaseZap,
  Eye,
  GitFork,
  History,
  Library,
  ListOrdered,
  Orbit,
  ChevronsUpDown,
  ToggleLeft,
  Sprout,
  Variable,
  Wrench,
} from 'lucide-react'
import {
  FIELD_ICONS,
  GENERATION_ICONS,
  SECTION_ICONS,
  TYPE_ICONS,
  auditSettingsIconCollisions,
  fieldIcon,
  generationIcon,
  sectionIcon,
} from './settingsIcons'

describe('settings icons', () => {
  it('gives every row its own glyph', () => {
    expect(auditSettingsIconCollisions()).toEqual([])
  })

  it('audits all four maps, not only fields and types', () => {
    const maps = [FIELD_ICONS, TYPE_ICONS, SECTION_ICONS, GENERATION_ICONS]
    const glyphs = maps.flatMap((map) =>
      Object.values(map).map((icon) => icon.displayName ?? 'anonymous'),
    )
    expect(new Set(glyphs).size).toBe(glyphs.length)
  })

  it('keeps the four formerly shared glyphs on one row each', () => {
    expect(SECTION_ICONS.memory).toBe(Library)
    expect(GENERATION_ICONS.memory_max_entries).toBe(ListOrdered)
    expect(SECTION_ICONS.hooks).toBe(Cable)
    expect(SECTION_ICONS.advanced).toBe(Wrench)
    expect(GENERATION_ICONS.max_tokens).toBe(Coins)
    const brainRows = [
      ...Object.values(FIELD_ICONS),
      ...Object.values(SECTION_ICONS),
      ...Object.values(GENERATION_ICONS),
    ].filter((icon) => icon === Brain)
    expect(brainRows).toHaveLength(1)
  })

  it('falls back to the variable glyph for an unknown generation lever', () => {
    expect(generationIcon('not_a_lever')).toBe(Variable)
  })

  it('keeps the registered field keys off the type fallback', () => {
    for (const key of Object.keys(FIELD_ICONS)) {
      expect(fieldIcon(key, 'bool')).toBe(FIELD_ICONS[key])
    }
  })

  it('maps the keys the design constitution names', () => {
    expect(FIELD_ICONS['chat.details_mode']).toBe(Eye)
    expect(FIELD_ICONS['cron.history_rows']).toBe(History)
    expect(FIELD_ICONS['memory.inject_max_entries']).toBe(DatabaseZap)
    expect(FIELD_ICONS['cron.max_parallel_jobs']).toBe(GitFork)
  })

  it('gives the type fallbacks distinct glyphs', () => {
    expect(fieldIcon('unregistered.key', 'bool')).toBe(ToggleLeft)
    expect(fieldIcon('unregistered.key', 'select')).toBe(ChevronsUpDown)
  })

  it('marks scheduled runs with the orbit glyph', () => {
    expect(sectionIcon('ephemera')).toBe(Orbit)
    // SOL's section arrives from the backend register; its header needs a glyph.
    expect(sectionIcon('sol')).toBe(Sprout)
  })
})
