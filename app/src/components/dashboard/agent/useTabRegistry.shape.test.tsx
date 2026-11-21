/**
 * #39 — the panel boot must survive valid JSON of the WRONG SHAPE.
 *
 * Measured: `ephe.panel.tabs` held `{"a":1}` and the boot called `.map` on it;
 * `ephe.panel.recent` held `[null]` and the boot read `.tab` of null. Invalid JSON
 * already fell back (readJson's catch), so the gap was the shape: JSON.parse
 * succeeded, the value just was not a tab inventory. Nothing around the boot
 * caught it, so the pane came up with a TypeError.
 *
 * GIVEN  a stored panel key with valid JSON that does not match the state's form
 * WHEN   the tab registry boots (the useState initialiser)
 * THEN   the documented default state comes back, without an exception
 * AND    a shape-valid stored value keeps every page (no user data is reset).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useTabRegistry } from './useTabRegistry'

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
}))

const DEFAULT_STATE = { open: ['preview'], active: 'preview', recent: [] }

function boot() {
  return renderHook(() => useTabRegistry()).result.current.tabState
}

describe('panel boot — ephe.panel.tabs with valid JSON of the wrong shape', () => {
  beforeEach(() => localStorage.clear())

  // object instead of array, bare string, numbers instead of page names,
  // null entries, JSON null/number/boolean instead of an inventory
  const badShapes = ['{"a":1}', '"x"', '[1,2]', '[null]', 'null', '42', 'true']

  for (const stored of badShapes) {
    it(`falls back to the default inventory for ${stored}`, () => {
      localStorage.setItem('ephe.panel.tabs', stored)
      expect(boot()).toEqual(DEFAULT_STATE)
    })
  }

  it('does not throw while booting (the measured TypeError)', () => {
    localStorage.setItem('ephe.panel.tabs', '{"a":1}')
    localStorage.setItem('ephe.panel.recent', '[null]')
    expect(() => boot()).not.toThrow()
  })
})

describe('panel boot — ephe.panel.recent with valid JSON of the wrong shape', () => {
  beforeEach(() => localStorage.clear())

  // object instead of array, numbers/nulls instead of entries, an entry whose
  // closedAt is missing, JSON null/number instead of a list
  const badShapes = ['{"a":1}', '"x"', '[1,2]', '[null]', '[{"tab":"git"}]', 'null', '42']

  for (const stored of badShapes) {
    it(`falls back to no recent entries for ${stored}`, () => {
      localStorage.setItem('ephe.panel.recent', stored)
      expect(boot().recent).toEqual([])
    })
  }
})

describe('panel boot — ephe.panel.activeTab with valid JSON of the wrong shape', () => {
  beforeEach(() => localStorage.clear())

  // An active page is a page name; an object/number/null is skew. The boot has to
  // open the first page instead of carrying the value into the bar.
  const badShapes = ['{"a":1}', 'null', '42', '[1]', 'true']

  for (const stored of badShapes) {
    it(`opens the first page for ${stored}`, () => {
      localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'git']))
      localStorage.setItem('ephe.panel.activeTab', stored)
      expect(boot().active).toBe('preview')
    })
  }
})

describe('panel boot — shape-valid state is not reset', () => {
  beforeEach(() => localStorage.clear())

  it('keeps a valid tab inventory, active page and recent list', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'git', 'memory']))
    localStorage.setItem('ephe.panel.activeTab', JSON.stringify('git'))
    localStorage.setItem('ephe.panel.recent', JSON.stringify([{ tab: 'memory', closedAt: 1234 }]))
    expect(boot()).toEqual({
      open: ['preview', 'git', 'memory'],
      active: 'git',
      recent: [{ tab: 'memory', closedAt: 1234 }],
    })
  })

  it('keeps an empty inventory (every pill closed) as empty', () => {
    localStorage.setItem('ephe.panel.tabs', '[]')
    expect(boot().open).toEqual([])
    expect(boot().active).toBeNull()
  })

  it('still accepts the legacy bare activeTab form', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'terminal']))
    localStorage.setItem('ephe.panel.activeTab', 'terminal')
    expect(boot().active).toBe('terminal')
  })

  it('drops an unknown page key but keeps the known ones', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'nope', 'git']))
    expect(boot().open).toEqual(['preview', 'git'])
  })
})
