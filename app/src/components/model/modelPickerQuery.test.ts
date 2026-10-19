/**
 * S2 — the picker's query rules, held where they are decided.
 *
 * The rule with teeth is the one a host cannot get wrong by accident: an unknown never
 * satisfies a filter, so a model whose tool support was never stated is neither a tools
 * model nor a non-tools model, and it stays out of a filtered list while still reading
 * as unknown in the plain one.
 */
import { describe, it, expect } from 'vitest'
import type { ModelRow } from './modelPickerTypes'
import { UNKNOWN_META, vendorPrefix } from './modelPickerTypes'
import {
  LONG_CONTEXT_MIN,
  formatContext,
  formatPricePair,
  matchesFilters,
  matchesQuery,
  searchRows,
  sectionRows,
  sortRows,
} from './modelPickerQuery'

function row(
  id: string,
  group: string,
  meta: Partial<ModelRow['meta']> = {},
  displayName: string | null = null,
): ModelRow {
  return {
    key: `${group}||${id}`,
    id,
    displayName,
    group,
    selectable: true,
    meta: { ...UNKNOWN_META, ...meta },
  }
}

const FREE = { isFree: true, priceInPerM: 0, priceOutPerM: 0 }
const PAID = { isFree: false, priceInPerM: 0.5, priceOutPerM: 2 }
const TOOLS = { supportsTools: true }
const BIG = { contextWindow: 200_000 }

describe('vendorPrefix', () => {
  it('reads a namespace the service wrote, and nothing else', () => {
    expect(vendorPrefix('openai/gpt-x')).toBe('openai')
    expect(vendorPrefix('gpt-x')).toBeNull()
    expect(vendorPrefix('/leading')).toBeNull()
    expect(vendorPrefix('trailing/')).toBeNull()
  })
})

describe('matchesFilters', () => {
  it('passes only a stated yes', () => {
    const yes = row('a', 'e', { supportsTools: true })
    const no = row('b', 'e', { supportsTools: false })
    const unknown = row('c', 'e')
    expect(matchesFilters(yes, ['tools'])).toBe(true)
    expect(matchesFilters(no, ['tools'])).toBe(false)
    expect(matchesFilters(unknown, ['tools'])).toBe(false)
  })

  it('treats long context as a stated number at or above the floor', () => {
    expect(matchesFilters(row('a', 'e', BIG), ['longContext'])).toBe(true)
    expect(
      matchesFilters(row('b', 'e', { contextWindow: LONG_CONTEXT_MIN - 1 }), ['longContext']),
    ).toBe(false)
    expect(matchesFilters(row('c', 'e'), ['longContext'])).toBe(false)
  })

  it('requires every active filter', () => {
    const both = row('a', 'e', { ...FREE, ...TOOLS })
    expect(matchesFilters(both, ['free', 'tools'])).toBe(true)
    expect(matchesFilters(row('b', 'e', FREE), ['free', 'tools'])).toBe(false)
  })
})

describe('matchesQuery', () => {
  const rows = [row('vendor/muse-4', 'openrouter', {}, 'Muse 4')]

  it('searches id, display name and provider, trimmed and case-folded', () => {
    for (const query of ['muse', '  MUSE  ', 'muse-4', 'openrouter', 'Muse 4']) {
      expect(matchesQuery(rows[0]!, query), query).toBe(true)
    }
    expect(matchesQuery(rows[0]!, 'nomodel')).toBe(false)
  })

  it('an empty query leaves the list alone', () => {
    expect(matchesQuery(rows[0]!, '   ')).toBe(true)
  })
})

describe('sortRows', () => {
  it('orders by name on the display name when there is one', () => {
    const rows = [row('zeta', 'e', {}, 'Alpha'), row('alpha', 'e', {}, 'Zeta')]
    expect(sortRows(rows, 'name').map((entry) => entry.id)).toEqual(['zeta', 'alpha'])
  })

  it('puts free first, then unknown, then priced', () => {
    const rows = [row('paid', 'e', PAID), row('unknown', 'e'), row('free', 'e', FREE)]
    expect(sortRows(rows, 'freeFirst').map((entry) => entry.id)).toEqual([
      'free',
      'unknown',
      'paid',
    ])
  })

  it('sorts known numbers and keeps the unknown ones behind them', () => {
    const rows = [
      row('small', 'e', { contextWindow: 1000 }),
      row('none', 'e'),
      row('big', 'e', BIG),
    ]
    expect(sortRows(rows, 'context').map((entry) => entry.id)).toEqual(['big', 'small', 'none'])
    const priced = [row('mid', 'e', { priceInPerM: 1 }), row('free', 'e', FREE), row('no', 'e')]
    expect(sortRows(priced, 'price').map((entry) => entry.id)).toEqual(['free', 'mid', 'no'])
  })
})

describe('sectionRows', () => {
  const rows = [
    row('openai/gpt-a', 'openrouter'),
    row('openai/gpt-b', 'openrouter'),
    row('muse-1', 'ephe'),
  ]

  it('stacks favorites, then recents, then the provider groups', () => {
    const sections = sectionRows(rows, ['muse-1'], ['openai/gpt-b'])
    expect(sections.map((section) => section.id)).toEqual(['favorites', 'recent', 'group-openai'])
    expect(sections[0]!.labelKey).toBe('modelPicker.favorites')
    expect(sections[1]!.rows.map((entry) => entry.id)).toEqual(['openai/gpt-b'])
  })

  it('shows a row once, so a favorite leaves its own group', () => {
    const sections = sectionRows(rows, ['muse-1'], [])
    const total = sections.reduce((sum, section) => sum + section.rows.length, 0)
    expect(total).toBe(rows.length)
    expect(sections.map((section) => section.id)).toEqual(['favorites', 'group-openai'])
  })

  it('ignores a stored id the engine no longer lists', () => {
    const sections = sectionRows(rows, ['gone/model'], ['also-gone'])
    expect(sections.map((section) => section.id)).toEqual(['group-ephe', 'group-openai'])
  })

  it('search and filter run before the sections', () => {
    const filtered = searchRows(rows, 'gpt', ['free'])
    expect(filtered).toEqual([])
    expect(searchRows(rows, 'gpt', []).map((entry) => entry.id)).toEqual([
      'openai/gpt-a',
      'openai/gpt-b',
    ])
  })
})

describe('the row cells a reader compares', () => {
  it('prints a token window as k, and nothing as the em-dash', () => {
    expect(formatContext(131072)).toBe('131k')
    expect(formatContext(8192)).toBe('8.2k')
    expect(formatContext(262144)).toBe('262k')
    expect(formatContext(900)).toBe('900')
    expect(formatContext(null)).toBeNull()
    expect(formatContext(0)).toBeNull()
  })

  it('prices both sides or neither', () => {
    expect(formatPricePair({ ...UNKNOWN_META, ...PAID })).toEqual({ in: '0.5', out: '2' })
    expect(formatPricePair({ ...UNKNOWN_META, ...FREE })).toEqual({ in: '0', out: '0' })
    expect(formatPricePair({ ...UNKNOWN_META, priceInPerM: 0.5 })).toBeNull()
    expect(formatPricePair(UNKNOWN_META)).toBeNull()
  })

  it('keeps two decimals where the cents matter', () => {
    expect(formatPricePair({ ...UNKNOWN_META, priceInPerM: 0.075, priceOutPerM: 0.3 })?.in).toBe(
      '0.08',
    )
  })
})
