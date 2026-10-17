/**
 * F6: one destination, one name, in each language.
 *
 * The register's exit said "Back to workspace", the workbench's said "back to the
 * task", the knowledge page's said "Back to work" — three labels for the surface
 * the user leaves, in a product that calls that thing a *task* everywhere else
 * (`nav.newTask`, `toolbar.*`, `artifacts.page.scopeSession`, the provenance
 * block). "Workspace" is worse than inconsistent: in this interface it already
 * names the folder on disk, which is a different thing the back button does not
 * return to.
 *
 * The rule is about the strings, so the strings are the test. It fails if a fourth
 * exit label appears with its own word, and if any of them drifts back.
 */
import { describe, it, expect } from 'vitest'
import en from './en.json'
import de from './de.json'

const BACK_KEYS = {
  register: (l: typeof en) => l.settings.back,
  workbench: (l: typeof en) => l.artifacts.page.back,
  knowledge: (l: typeof en) => l.memory.back,
  // WD-33: the register of workspaces is the fourth full-page surface that leaves to the
  // task, and it carries its own key for the same reason the other three do — the word is
  // one, the surface that says it keeps its own name for it.
  workspaces: (l: typeof en) => l.workspaces.back,
}

describe('the exit of a full-page surface', () => {
  it('uses one word in English', () => {
    const values = Object.values(BACK_KEYS).map((get) => get(en))
    expect(new Set(values).size).toBe(1)
    expect(values[0]).toMatch(/\btask\b/)
  })

  it('uses one word in German', () => {
    const values = Object.values(BACK_KEYS).map((get) => get(de as typeof en))
    expect(new Set(values).size).toBe(1)
    expect(values[0]).toContain('Aufgabe')
  })

  it('does not call the destination a workspace or a job', () => {
    for (const [lng, bundle] of [
      ['en', en],
      ['de', de as typeof en],
    ] as const) {
      for (const [name, get] of Object.entries(BACK_KEYS)) {
        const value = get(bundle)
        expect(value, `${lng} ${name}`).not.toMatch(/workspace|Workspace|Arbeit/)
      }
    }
  })

  it('writes the sentence the same way every time', () => {
    for (const [lng, bundle] of [
      ['en', en],
      ['de', de as typeof en],
    ] as const) {
      for (const [name, get] of Object.entries(BACK_KEYS)) {
        expect(get(bundle), `${lng} ${name}`).toMatch(/^[A-ZÄÖÜ]/)
      }
    }
  })
})
