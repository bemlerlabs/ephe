import { Tab } from './primitives'

/**
 * C1: the column answers one question — what does this task show me right now.
 *
 * Nine tab kinds sat in one flat bar, so a document, a dev server, a terminal,
 * an audit log and a side conversation all asked for the same attention at the
 * same height. A section groups the kinds that belong to one answer, and the
 * header shows one icon per section that actually has something open: click it
 * to bring that section forward, click the one already forward to fold the body
 * away and give the reading width back to the chat.
 */
export type Section = 'output' | 'site' | 'console' | 'notes' | 'review'

/** The order the row draws in — what a task produces first, last. */
export const SECTION_ORDER: readonly Section[] = ['output', 'site', 'console', 'notes', 'review']

export const SECTION_OF: Record<Tab, Section> = {
  files: 'output',
  preview: 'site',
  browser: 'site',
  terminal: 'console',
  audit: 'console',
  trajectory: 'console',
  subagents: 'console',
  memory: 'notes',
  side: 'notes',
  git: 'review',
}

/** One icon per section, borrowed from the kind that represents it, so the row
 *  and the pills inside it never disagree about what a thing looks like. */
export const SECTION_LEAD: Record<Section, Tab> = {
  output: 'files',
  site: 'preview',
  console: 'terminal',
  notes: 'memory',
  review: 'git',
}

/** The sections this set of tabs touches, in draw order. */
export function sectionsOf(open: readonly Tab[]): Section[] {
  const seen = new Set<Section>()
  for (const tab of open) seen.add(SECTION_OF[tab])
  return SECTION_ORDER.filter((section) => seen.has(section))
}

export function tabsIn(open: readonly Tab[], section: Section): Tab[] {
  return open.filter((tab) => SECTION_OF[tab] === section)
}

/** The section the reader is looking at, or none while nothing is selected. */
export function sectionOfActive(active: Tab | null | undefined): Section | null {
  return active ? SECTION_OF[active] : null
}

/** The tab a section click selects: the one already active in it, else the
 *  first the register holds — a section is never clicked into an empty body. */
export function leadTab(open: readonly Tab[], section: Section, active: Tab | null): Tab | null {
  const tabs = tabsIn(open, section)
  if (!tabs.length) return null
  if (active && SECTION_OF[active] === section) return active
  return tabs[0] ?? null
}
