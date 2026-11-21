// I7-6: the bottom save bar is either justified for a section or it is not.
// It is justified where the deep register keeps its fields — there it saves
// exactly what the user just touched. Where every click has its own endpoint,
// it was a button that saved the engine while the user was touching a
// persona, a voice or a server list.
import { describe, it, expect } from 'vitest'

import { NAV } from './model'
import { SECTION_TAB } from './model/deepRegister'
import { READONLY_TABS, type TabKey } from './types'

/** Sections whose controls write into the `settings` draft (no register). */
const DRAFT_TABS: TabKey[] = ['generation']

/** The one surface whose register rows persist on change, through the register path. */
const INSTANT_TABS: TabKey[] = ['appearance']

describe('the footer save follows the rule of one store per area', () => {
  it('no register area stands on the read-only list', () => {
    const registerTabs = new Set(Object.values(SECTION_TAB))
    const clash = [...registerTabs].filter((tab) => READONLY_TABS.has(tab as TabKey))
    expect(clash).toEqual([])
  })

  it('every nav area is decided: register, draft or instant', () => {
    const registerTabs = new Set(Object.values(SECTION_TAB))
    const undecided = NAV.map((n) => n.key).filter(
      (tab) =>
        !registerTabs.has(tab) &&
        !READONLY_TABS.has(tab) &&
        !DRAFT_TABS.includes(tab) &&
        !INSTANT_TABS.includes(tab),
    )
    expect(undecided).toEqual([])
  })

  it('appearance is the one instant surface and still a register tab', () => {
    expect(INSTANT_TABS).toEqual(['appearance'])
    expect(READONLY_TABS.has('appearance')).toBe(false)
    expect(Object.values(SECTION_TAB)).toContain('appearance')
  })

  it('the instant areas are named and never merely absent', () => {
    for (const tab of ['skills', 'mcp', 'persona', 'voice', 'mobile', 'privacy', 'code-exec']) {
      expect(READONLY_TABS.has(tab as TabKey), tab).toBe(true)
    }
  })
})
