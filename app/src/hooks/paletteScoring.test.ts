/**
 * The command palette's pure building blocks: the Cmd/Ctrl+K toggle test, the
 * weighted fuzzy scorer, and the best-effort usage-frequency store. These are
 * the functions `useCommandPalette` is built from; each is exercised on its own
 * so a scoring regression shows up without rendering the palette.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  bumpFreq,
  frecencyMultiplier,
  frecencyScore,
  fuzzyScore,
  isPaletteToggle,
  readFrecency,
  readFreq,
} from './paletteScoring'

const FREQ_KEY = 'ephe_cmd_freq'

describe('isPaletteToggle', () => {
  it('accepts Cmd/Ctrl + K case-independently', () => {
    expect(isPaletteToggle({ key: 'k', metaKey: true })).toBe(true)
    expect(isPaletteToggle({ key: 'K', ctrlKey: true })).toBe(true)
  })

  it('accepts the KeyK code when the key label is not "k"', () => {
    expect(isPaletteToggle({ key: 'Dead', code: 'KeyK', metaKey: true })).toBe(true)
  })

  it('rejects without a modifier', () => {
    expect(isPaletteToggle({ key: 'k' })).toBe(false)
  })

  it('rejects another key', () => {
    expect(isPaletteToggle({ key: 'j', metaKey: true })).toBe(false)
  })
})

describe('fuzzyScore', () => {
  const item = { label: 'Open Settings', section: 'Navigation' }

  it('an empty query matches everything weakly', () => {
    expect(fuzzyScore(item, '')).toBe(1)
  })

  it('a prefix hit is the strongest signal', () => {
    const prefix = fuzzyScore(item, 'open')
    expect(prefix).toBe(1000 - 'open settings'.length)
    expect(prefix).toBeGreaterThan(fuzzyScore(item, 'sett'))
  })

  it('a non-prefix subsequence scores positive', () => {
    expect(fuzzyScore(item, 'osg')).toBeGreaterThan(0)
  })

  it('a non-match scores zero', () => {
    expect(fuzzyScore(item, 'zzz')).toBe(0)
  })

  it('a section substring adds a weak bonus', () => {
    // 'se' is a word-boundary (word-prefix) hit on both items, so the tiers tie
    // and the section substring decides between the two otherwise-equal items.
    const withSection = fuzzyScore({ label: 'Open Settings', section: 'Settings' }, 'se')
    const without = fuzzyScore({ label: 'Open Settings', section: 'Navigation' }, 'se')
    expect(withSection).toBe(without + 2)
  })
})

describe('fuzzyScore tiers (prefix > word-boundary > subsequence)', () => {
  const settings = { label: 'Open settings', section: 'Navigation' }
  const switchSide = { label: "Switch Ephe's Computer side (left/right)", section: 'Navigation' }

  // P1-3: the audit's reproduction (team-d-ui-deltas.md item 1). Before the fix
  // 'sett' scored Switch...side 54 (scattered, one uppercase edge) against
  // Open settings 50 (one contiguous run inside the word), so the scattered row led.
  it("ranks the settings command above the scattered match for 'sett'", () => {
    const word = fuzzyScore(settings, 'sett')
    const scattered = fuzzyScore(switchSide, 'sett')
    expect(word).toBeGreaterThan(0)
    expect(scattered).toBeGreaterThan(0)
    expect(word).toBeGreaterThan(scattered)
  })

  it('orders the three tiers strictly on one item', () => {
    const prefix = fuzzyScore(settings, 'open')
    const boundary = fuzzyScore(settings, 'sett')
    const scattered = fuzzyScore(settings, 'osg')
    expect(prefix).toBeGreaterThan(boundary)
    expect(boundary).toBeGreaterThan(scattered)
  })

  it('puts every word-boundary hit in its own band above every subsequence', () => {
    expect(fuzzyScore(settings, 'sett')).toBeGreaterThanOrEqual(700)
    expect(fuzzyScore(switchSide, 'sett')).toBeLessThan(700)
    expect(fuzzyScore(settings, 'osg')).toBeLessThan(700)
  })

  it('treats each separator as a word start, case-independently', () => {
    expect(fuzzyScore({ label: 'left-right', section: 'x' }, 'right')).toBeGreaterThanOrEqual(700)
    expect(fuzzyScore({ label: 'panel/git', section: 'x' }, 'git')).toBeGreaterThanOrEqual(700)
    expect(fuzzyScore({ label: 'a·b', section: 'x' }, 'b')).toBeGreaterThanOrEqual(700)
    expect(fuzzyScore({ label: 'top–bottom', section: 'x' }, 'bottom')).toBeGreaterThanOrEqual(700)
    expect(fuzzyScore({ label: 'Zero-based', section: 'x' }, 'BASED')).toBeGreaterThanOrEqual(700)
  })

  it('does not promote a contiguous run that sits inside a word', () => {
    // 'avi' is contiguous inside 'Navigation' (index 1), not at a word start.
    expect(fuzzyScore({ label: 'Navigation', section: 'x' }, 'avi')).toBeLessThan(700)
  })
})

describe('readFreq / bumpFreq', () => {
  beforeEach(() => localStorage.clear())

  it('empty storage reads an empty map', () => {
    expect(readFreq()).toEqual({})
  })

  it('bumpFreq increments the per-command counter', () => {
    bumpFreq('a')
    bumpFreq('a')
    bumpFreq('b')
    expect(readFreq()).toEqual({ a: 2, b: 1 })
  })

  it('corrupt storage degrades to an empty map', () => {
    localStorage.setItem(FREQ_KEY, '{not json')
    expect(readFreq()).toEqual({})
  })

  it('bumpFreq survives a storage write failure (private mode)', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => bumpFreq('x')).not.toThrow()
    spy.mockRestore()
  })
})

const WEEK_MS = 7 * 24 * 60 * 60 * 1000
const NOW = 1_700_000_000_000

describe('frecency (recency-weighted, weekly decay)', () => {
  beforeEach(() => localStorage.clear())

  it('stores a readable {count, lastUsedAt} entry', () => {
    bumpFreq('a')
    expect(readFrecency()['a']).toEqual({ count: 1, lastUsedAt: expect.any(Number) })
    expect(readFrecency()['a']!.lastUsedAt).toBeGreaterThan(0)
    // the raw persisted value is the same readable map
    expect(JSON.parse(localStorage.getItem(FREQ_KEY)!)).toEqual({
      a: { count: 1, lastUsedAt: expect.any(Number) },
    })
  })

  it('readFreq stays a plain count map, so existing readers are untouched', () => {
    bumpFreq('a')
    bumpFreq('a')
    bumpFreq('b')
    expect(readFreq()).toEqual({ a: 2, b: 1 })
  })

  it('grows with count and halves every week', () => {
    const fresh = frecencyMultiplier({ count: 5, lastUsedAt: NOW }, NOW)
    expect(fresh).toBeGreaterThan(frecencyMultiplier({ count: 1, lastUsedAt: NOW }, NOW))
    expect(frecencyMultiplier({ count: 5, lastUsedAt: NOW - WEEK_MS }, NOW)).toBeCloseTo(
      fresh / 2,
      10,
    )
    expect(frecencyMultiplier({ count: 5, lastUsedAt: NOW - 2 * WEEK_MS }, NOW)).toBeCloseTo(
      fresh / 4,
      10,
    )
  })

  it('is neutral for an unused command', () => {
    expect(frecencyMultiplier(undefined, NOW)).toBe(1)
    expect(frecencyMultiplier({ count: 0, lastUsedAt: NOW }, NOW)).toBe(1)
    expect(frecencyScore(42, undefined, NOW)).toBe(42)
  })

  it('feeds future timestamps no negative decay', () => {
    const future = frecencyMultiplier({ count: 3, lastUsedAt: NOW + WEEK_MS }, NOW)
    expect(future).toBeCloseTo(frecencyMultiplier({ count: 3, lastUsedAt: NOW }, NOW), 10)
  })

  it('an old count decays below neutral — the top can no longer be pinned', () => {
    expect(frecencyMultiplier({ count: 20, lastUsedAt: NOW - 8 * WEEK_MS }, NOW)).toBeLessThan(1)
  })

  // P1-3: the audit's second reproduction (team-d-ui-deltas.md item 2). Seeding
  // {count: 5} for a scattered match promoted it above the exact-prefix 'Steps'.
  it('a fresh count cannot leapfrog an exact-prefix match', () => {
    const steps = { label: 'Steps', section: 'Navigation' }
    const prefix = fuzzyScore(steps, 'st')
    const pin: { count: number; lastUsedAt: number } = { count: 5, lastUsedAt: NOW }
    // the audit's seeded row, and a row whose 'st' is truly scattered
    const seeded = {
      label: "Close Ephe's Computer / dialog · stop generation",
      section: 'Navigation',
    }
    const scattered = { label: "Close Ephe's dialog · halt", section: 'Navigation' }
    expect(fuzzyScore(scattered, 'st')).toBeGreaterThan(0)
    expect(fuzzyScore(scattered, 'st')).toBeLessThan(700)
    expect(frecencyScore(fuzzyScore(scattered, 'st'), pin, NOW)).toBeLessThan(prefix)
    expect(frecencyScore(fuzzyScore(seeded, 'st'), pin, NOW)).toBeLessThan(prefix)
    // the boost is real, just bounded: the seeded row outranks its own unboosted score
    expect(frecencyScore(fuzzyScore(seeded, 'st'), pin, NOW)).toBeGreaterThan(
      fuzzyScore(seeded, 'st'),
    )
  })

  it('migrates a legacy bare-count map as fully decayed', () => {
    localStorage.setItem(FREQ_KEY, JSON.stringify({ a: 5 }))
    expect(readFreq()).toEqual({ a: 5 })
    expect(readFrecency()['a']).toEqual({ count: 5, lastUsedAt: 0 })
    expect(frecencyMultiplier(readFrecency()['a'], NOW)).toBeLessThan(1)
  })

  it('bumping a legacy entry upgrades it to the timestamped shape', () => {
    localStorage.setItem(FREQ_KEY, JSON.stringify({ a: 5 }))
    bumpFreq('a')
    expect(readFrecency()['a']).toMatchObject({ count: 6 })
    expect(readFrecency()['a']!.lastUsedAt).toBeGreaterThan(0)
  })
})
