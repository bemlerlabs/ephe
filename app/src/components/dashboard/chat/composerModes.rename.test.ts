/**
 * Task 3 guard — the renamed composer vocabulary is one contract.
 *
 * The owner ruled the new names: ask becomes Analyst, plan becomes Architect,
 * full-access becomes Operator, and `creator` entered the menu with Wave 5,
 * when the consent gate and the four bundle tools behind the name landed
 * (`80e3852f`, `b4daa41c`). edit-auto retires from the menu only: its stored
 * value keeps resolving to the edit-family compatibility factor, so no session
 * gains or loses an approval through the rename. Three surfaces state that
 * vocabulary — the tile list, the two locale bundles, and the stored legacy
 * values a session may carry from before the rename — and all three have to
 * move together, because a tile list the locales do not name is exactly the
 * kind of surface that promises something the engine does not run.
 */
import { describe, expect, it } from 'vitest'
import en from '@/locales/en.json'
import de from '@/locales/de.json'
import { SESSION_MODES } from './modeCatalog'
import {
  COMPAT_EDIT_FAMILY_MODE,
  DEFAULT_COMPOSER_MODE,
  MIGRATABLE_LEGACY_MODES,
  normalizeComposerMode,
} from '@/store/chat/helpers'

type HintBundle = {
  chat: { modeHint: Record<string, string>; modeSection: Record<string, string> }
}
const enChat = (en as unknown as HintBundle).chat
const deChat = (de as unknown as HintBundle).chat

describe('the renamed composer vocabulary', () => {
  it('has four selectable modes and no retired edit-auto', () => {
    expect(SESSION_MODES.map((m) => m.key)).toEqual(['analyst', 'architect', 'operator', 'creator'])
  })

  it('gives the creator tile the section the bundles already name', () => {
    // Wave 5's condition was a guard and tools behind the name; both landed in
    // `80e3852f`, so the tile now has to say what that gate actually does.
    const creator = SESSION_MODES.find((m) => m.key === 'creator')!
    expect(creator.sectionKey).toBe('chat.modeSection.create')
    expect(creator.hintKey).toBe('chat.modeHint.creator')
    expect(Object.keys(enChat.modeSection)).toContain('create')
    expect(Object.keys(deChat.modeSection)).toContain('create')
    // The English sentence names the three permissions by the names the guard
    // stores, because a tile that promises "more freedom" is not a contract.
    const enHint = String(enChat.modeHint.creator)
    for (const permission of ['code', 'files', 'network']) {
      expect(enHint.toLowerCase()).toContain(permission)
    }
    expect(enHint).toContain('—')
  })

  it('names every mode before the em dash in both languages', () => {
    for (const mode of SESSION_MODES) {
      const hintEn = enChat.modeHint[mode.key]
      const hintDe = deChat.modeHint[mode.key]
      expect(String(hintEn).split(' — ')[0]).not.toBe(mode.key)
      expect(String(hintDe).includes(' — ')).toBe(true)
    }
  })

  it('defaults a fresh session to a tool-capable mode (same sense as before)', () => {
    expect(DEFAULT_COMPOSER_MODE).toBe('operator')
  })

  it('resolves each migratable legacy value to one current mode key', () => {
    expect(normalizeComposerMode('ask')).toBe('analyst')
    expect(normalizeComposerMode('plan')).toBe('architect')
    expect(normalizeComposerMode('full-access')).toBe('operator')
    expect(normalizeComposerMode(undefined)).toBe(DEFAULT_COMPOSER_MODE)
  })

  it('keeps the retired edit-auto exactly as stored, on the wire', () => {
    // Per-profile equivalence, client half (the server half lives in
    // tests/test_composer_mode_rename.py): the menu retired the tile, the
    // alias table still answers `edit-auto` with the edit-family factor, and
    // the session keeps asking for everything outside that family under every
    // approval profile. Rewriting the stored value to a tile would hand the
    // session a wider ceiling — a rename may move names, never privileges.
    expect(MIGRATABLE_LEGACY_MODES.has('edit-auto')).toBe(false)
    expect(normalizeComposerMode('edit-auto')).toBe(COMPAT_EDIT_FAMILY_MODE)
    expect(COMPAT_EDIT_FAMILY_MODE).toBe('edit-auto')
  })

  it('never lets an untiled wire value into the ComposerMode union', () => {
    // `agent` is the legacy all-factors value: it keeps its stored spelling
    // through the normalizer, as does any mode another client sends. `creator`
    // is a tile now, so it resolves to itself by being listed, not by being
    // passed through.
    expect(normalizeComposerMode('agent')).toBe('agent')
    expect(normalizeComposerMode('creator')).toBe('creator')
    expect(normalizeComposerMode('something-else')).toBe('something-else')
  })
})
