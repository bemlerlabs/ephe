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

describe('die Fuss-Save folgt der Regel "ein Speicher, den der Bereich braucht"', () => {
  it('kein Register-Bereich steht auf der Leseliste', () => {
    const registerTabs = new Set(Object.values(SECTION_TAB))
    const clash = [...registerTabs].filter((tab) => READONLY_TABS.has(tab as TabKey))
    expect(clash).toEqual([])
  })

  it('jeder Navigationsbereich ist entschieden: Register, Entwurf oder sofortwirkend', () => {
    const registerTabs = new Set(Object.values(SECTION_TAB))
    const undecided = NAV.map((n) => n.key).filter(
      (tab) => !registerTabs.has(tab) && !READONLY_TABS.has(tab) && !DRAFT_TABS.includes(tab),
    )
    expect(undecided).toEqual([])
  })

  it('die sofortwirkenden Bereiche sind benannt, nicht nur abwesend', () => {
    for (const tab of ['skills', 'mcp', 'persona', 'voice', 'mobile', 'privacy', 'code-exec']) {
      expect(READONLY_TABS.has(tab as TabKey), tab).toBe(true)
    }
  })
})
