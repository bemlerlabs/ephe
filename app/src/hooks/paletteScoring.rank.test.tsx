/**
 * R63: the register's reproduction — a scattered match with a stored use count
 * ranked above an exact-prefix match. The pure scorer already carried the
 * word-boundary tier and the frecency helpers, but the palette itself still
 * ordered each section by the bare count and never by the decayed frecency, so
 * the live panel kept the mis-ranking. These tests drive the real hook, so the
 * order asserted here is the order the panel renders.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'

const api = vi.hoisted(() => ({
  searchSessionContent: vi.fn(),
  fileUrl: vi.fn((p: string) => p),
}))
vi.mock('@/lib/api', () => api)

const native = vi.hoisted(() => ({ openExternally: vi.fn(async () => {}) }))
vi.mock('@/lib/nativeBrowser', () => native)

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string) => k,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

import { useCommandPalette } from './useCommandPalette'
import { frecencyMultiplier, fuzzyScore, groupBySection, paletteRankKey } from './paletteScoring'
import { useChatStore } from '@/store/chatStore'

const FREQ_KEY = 'ephe_cmd_freq'
const WEEK_MS = 7 * 24 * 60 * 60 * 1000
const SETTINGS_SECTION = 'commandPalette.sections.settings'

function wrapper({ children }: { children: ReactNode }) {
  return createElement(MemoryRouter, null, children)
}

function seedFreq(map: Record<string, { count: number; lastUsedAt: number }>) {
  localStorage.setItem(FREQ_KEY, JSON.stringify(map))
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null })
})

describe('R63: the palette ranks an exact prefix above a scattered match', () => {
  // The audit's seeded row: 'commandPalette.items.settings' (id 'settings') ran 5
  // times. For the query 'settings' it is a scattered (subsequence) match, while
  // the 'settings.<key>' rows are exact-prefix hits in the very same section.
  it('a scattered row with count 5 no longer outranks the exact-prefix rows', () => {
    seedFreq({ settings: { count: 5, lastUsedAt: Date.now() } })

    const { result } = renderHook(() => useCommandPalette(), { wrapper })
    act(() => result.current.setQuery('settings'))

    const rows = result.current.grouped[SETTINGS_SECTION]!
    const scattered = rows.findIndex((r) => r.id === 'settings')
    const prefix = rows.findIndex((r) => r.id.startsWith('settings-'))
    expect(prefix).toBeGreaterThanOrEqual(0)
    expect(scattered).toBeGreaterThanOrEqual(0)
    expect(scattered).toBeGreaterThan(prefix)
    expect(rows[0]!.id.startsWith('settings-')).toBe(true)
  })

  // The time half of the register: a command used once long ago must not pin the
  // top forever. Both rows share a tier here, so only the decayed frecency decides.
  it('a once-hot command decays: an eight-week-old count no longer leads', () => {
    seedFreq({ settings: { count: 20, lastUsedAt: Date.now() - 8 * WEEK_MS } })

    const { result } = renderHook(() => useCommandPalette(), { wrapper })

    const rows = result.current.grouped[SETTINGS_SECTION]!
    expect(rows[0]!.id).not.toBe('settings')
  })

  it('a fresh count still leads its own section (the boost is real, not gone)', () => {
    seedFreq({ settings: { count: 3, lastUsedAt: Date.now() } })

    const { result } = renderHook(() => useCommandPalette(), { wrapper })

    const rows = result.current.grouped[SETTINGS_SECTION]!
    expect(rows[0]!.id).toBe('settings')
  })
})

describe('R63: paletteRankKey — tiers dominate, frecency only breaks ties', () => {
  const NOW = 1_700_000_000_000
  const fresh = { count: 5, lastUsedAt: NOW }
  const steps = { id: 'steps', label: 'Steps', section: 'Navigation' }
  const scattered = { id: 'close', label: "Close Ephe's dialog · halt", section: 'Navigation' }

  it('a fresh counted scattered row cannot leapfrog the exact prefix', () => {
    const freq = { close: fresh }
    expect(fuzzyScore(scattered, 'st')).toBeGreaterThan(0)
    expect(fuzzyScore(scattered, 'st')).toBeLessThan(700)
    expect(paletteRankKey(steps, 'st', freq, NOW)).toBeGreaterThan(
      paletteRankKey(scattered, 'st', freq, NOW),
    )
  })

  it('no count is large enough to cross a tier — the boost stays under one', () => {
    const huge = { count: 1_000_000, lastUsedAt: NOW }
    const freq = { close: huge }
    const boosted = paletteRankKey(scattered, 'st', freq, NOW)
    const tier = fuzzyScore(scattered, 'st')
    expect(boosted).toBeGreaterThan(tier) // the boost is real
    expect(boosted).toBeLessThan(tier + 1) // but bounded below the next integer tier
    expect(paletteRankKey(steps, 'st', freq, NOW)).toBeGreaterThan(boosted)
  })

  it('a word-boundary hit outranks a scattered run despite a fresh count', () => {
    const word = { id: 'w', label: 'Open settings', section: 'Navigation' }
    const other = { id: 's', label: "Switch Ephe's Computer side (left/right)", section: 'x' }
    const freq = { s: fresh }
    expect(fuzzyScore(word, 'sett')).toBeGreaterThanOrEqual(700)
    expect(paletteRankKey(word, 'sett', freq, NOW)).toBeGreaterThan(
      paletteRankKey(other, 'sett', freq, NOW),
    )
  })

  it('among equal tiers the fresher, heavier row leads', () => {
    // both five characters, so the prefix tier (1000 − len) gives the same score
    const a = { id: 'a', label: 'Steps', section: 'x' }
    const b = { id: 'b', label: 'Start', section: 'x' }
    expect(fuzzyScore(a, 'st')).toBe(fuzzyScore(b, 'st'))
    const freq = { a: { count: 1, lastUsedAt: NOW }, b: { count: 9, lastUsedAt: NOW } }
    expect(paletteRankKey(b, 'st', freq, NOW)).toBeGreaterThan(paletteRankKey(a, 'st', freq, NOW))
  })

  it('decays: a long-unused count ranks below no count at all', () => {
    const item = { id: 'w', label: 'Open settings', section: 'Navigation' }
    const stale = { w: { count: 20, lastUsedAt: NOW - 8 * WEEK_MS } }
    expect(paletteRankKey(item, 'sett', stale, NOW)).toBeLessThan(
      paletteRankKey(item, 'sett', {}, NOW),
    )
  })

  it('a raw product would be unsafe — the reason for the fraction, not a multiplier', () => {
    // the multiplier is unbounded in `count`; 3.07 × the 499 subsequence cap clears
    // the 900 prefix floor, so a product could lift a hot scattered row over a prefix.
    const huge = frecencyMultiplier({ count: 1_000_000, lastUsedAt: NOW }, NOW)
    expect(huge).toBeGreaterThan(3)
    expect(huge * 499).toBeGreaterThan(900)
  })
})

describe('R63: groupBySection — a section leads with its best match', () => {
  const NOW = 1_700_000_000_000
  const rows = [
    { id: 'close', label: "Close Ephe's dialog · halt", section: 'Navigation' },
    { id: 'steps', label: 'Steps', section: 'Navigation' },
  ]

  it('the exact prefix leads even when the scattered row was run five times', () => {
    const grouped = groupBySection(rows, 'st', { close: { count: 5, lastUsedAt: NOW } }, NOW)
    expect(grouped['Navigation']!.map((r) => r.id)).toEqual(['steps', 'close'])
  })

  it('keeps the input order for equal ranks (sessions stay chronological)', () => {
    const grouped = groupBySection(rows, '', {}, NOW)
    expect(grouped['Navigation']!.map((r) => r.id)).toEqual(['close', 'steps'])
  })
})
