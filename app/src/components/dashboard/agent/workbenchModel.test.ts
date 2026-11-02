/**
 * C1: the column groups what a task shows into sections, and the row draws one
 * icon per section that holds something open.
 */
import { describe, it, expect } from 'vitest'
import type { Tab } from './primitives'
import {
  SECTION_OF,
  SECTION_ORDER,
  leadTab,
  sectionOfActive,
  sectionsOf,
  tabsIn,
} from './workbenchModel'

const EVERY_KIND: Tab[] = [
  'preview',
  'browser',
  'terminal',
  'git',
  'files',
  'audit',
  'trajectory',
  'subagents',
  'memory',
  'side',
]

describe('workbenchModel', () => {
  it('gives every tab kind exactly one section, and every section a lead', () => {
    for (const tab of EVERY_KIND) {
      expect(SECTION_OF[tab]).toBeTruthy()
      expect(SECTION_ORDER).toContain(SECTION_OF[tab])
    }
  })

  it('draws each section once, in the order a task produces them', () => {
    expect(sectionsOf(['memory', 'files', 'preview', 'audit'])).toEqual([
      'output',
      'site',
      'console',
      'notes',
    ])
    expect(sectionsOf([])).toEqual([])
    expect(sectionsOf(['terminal', 'audit', 'subagents'])).toEqual(['console'])
  })

  it('keeps the register order inside a section', () => {
    expect(tabsIn(['terminal', 'preview', 'audit'], 'console')).toEqual(['terminal', 'audit'])
  })

  it('brings a section forward on its own tab, or on the first it holds', () => {
    expect(leadTab(['files', 'terminal'], 'console', 'files')).toBe('terminal')
    expect(leadTab(['files', 'terminal', 'audit'], 'console', 'terminal')).toBe('terminal')
    expect(leadTab(['files'], 'console', 'files')).toBeNull()
  })

  it('names no section while nothing is selected', () => {
    expect(sectionOfActive(null)).toBeNull()
    expect(sectionOfActive(undefined)).toBeNull()
    expect(sectionOfActive('git')).toBe('review')
  })
})
