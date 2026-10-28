import { describe, expect, it } from 'vitest'
import {
  DatabaseZap,
  Eye,
  GitFork,
  History,
  Orbit,
  ChevronsUpDown,
  ToggleLeft,
} from 'lucide-react'
import {
  FIELD_ICONS,
  auditSettingsIconCollisions,
  fieldIcon,
  sectionIcon,
} from './settingsIcons'

describe('settings icons', () => {
  it('gives every row its own glyph', () => {
    expect(auditSettingsIconCollisions()).toEqual([])
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
  })
})
