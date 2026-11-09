/**
 * W-3 — the mode chip says the same word out loud as it shows.
 *
 * Measured on 2026-11-02 in the shipped app: the button read `Profile: Full access` on
 * screen while its accessible name was `Composer response mode · Manual`. A screen-reader
 * user was told the approval profile, a seeing user the composer mode — two different
 * settings that the composer shows in two different chips. The word `Manual` was not even
 * the value under the label: `chat.perm.*` names the security profile, which the approvals
 * chip at ChatInput.tsx already owns, with its own aria-label and its own text.
 *
 * These witnesses hold the pair the finding broke: the name contains the visible mode
 * label, and the profile word appears in no part of this chip. Both halves run in English
 * and German, because the label is cut out of the translated hint text.
 */
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useRef } from 'react'

const EN: Record<string, string> = {
  'chat.modeSelectorAria': 'Composer response mode',
  'chat.modeHint.analyst': 'Analyst — Ephe answers, no tools run',
  'chat.modeHint.architect': 'Architect — Ephe drafts a plan first; nothing runs until you confirm',
  'chat.modeHint.operator': 'Operator — every tool runs without asking',
  'chat.modeSection.write': 'With write access',
  'chat.perm.strict': 'Manual',
}

const DE: Record<string, string> = {
  'chat.modeSelectorAria': 'Antwort-Modus des Composers', // language-gate: ignore
  'chat.modeHint.analyst': 'Analyst — Ephe antwortet nur, keine Werkzeuge laufen', // language-gate: ignore
  'chat.modeHint.architect':
    'Architekt — Ephe entwirft erst einen Plan; nichts läuft ohne deine Bestätigung', // language-gate: ignore
  'chat.modeHint.operator': 'Operator — jedes Werkzeug läuft ohne Rückfrage', // language-gate: ignore
  'chat.modeSection.write': 'Mit Schreibzugriff', // language-gate: ignore
  'chat.perm.strict': 'Manuell', // language-gate: ignore
}

/** The three modes, in the order the menu lists them. */
const MODES = ['analyst', 'architect', 'operator'] as const

let table: Record<string, string> = EN

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string) => table[key] ?? key,
  }),
}))

import ComposerModeChip from './chat/ComposerModeChip'

function renderChip(mode: string) {
  function Host() {
    const ref = useRef<HTMLButtonElement>(null)
    return (
      <ComposerModeChip
        open={false}
        mode={mode}
        anchorRef={ref}
        menuPos={null}
        onToggle={() => undefined}
        onClose={() => undefined}
        onPick={() => undefined}
      />
    )
  }
  return render(<Host />)
}

const shortLabel = (catalog: Record<string, string>, mode: string) =>
  catalog[`chat.modeHint.${mode}`]!.split('—')[0]!.trim()

describe.each([
  ['English', EN],
  ['German', DE],
])('%s: one word on the chip and in its name', (_lang, catalog) => {
  beforeAll(() => {
    table = catalog
  })

  it.each(MODES)('names the mode it shows — %s', (mode) => {
    const label = shortLabel(catalog, mode)
    renderChip(mode)
    const chip = screen.getByTestId('composer-mode-selector')
    expect(chip.textContent, 'visible text').toContain(label)
    expect(chip.getAttribute('aria-label'), 'accessible name').toContain(label)
  })

  it('keeps the approval profile out of both halves', () => {
    renderChip('operator')
    const chip = screen.getByTestId('composer-mode-selector')
    const profileWord = catalog['chat.perm.strict']!
    // The profile has its own chip; naming it here is the contradiction the finding saw.
    expect(chip.textContent).not.toContain(profileWord)
    expect(chip.getAttribute('aria-label')).not.toContain(profileWord)
    // The visible text is the mode alone — no word over it that names a different setting.
    expect(chip.textContent, 'the chip shows the mode and nothing else').toBe(
      shortLabel(catalog, 'operator'),
    )
  })

  it('names the section, with no raw key, for a stored mode that owns no tile', () => {
    // Task 3: the retired `edit-auto` stays on the wire for the sessions that
    // stored it. The chip renders the section wording the locale already owns.
    renderChip('edit-auto')
    const chip = screen.getByTestId('composer-mode-selector')
    expect(chip.textContent, 'visible text').toBe(catalog['chat.modeSection.write'])
    expect(chip.getAttribute('aria-label'), 'accessible name').toContain(
      catalog['chat.modeSection.write'],
    )
    expect(chip.textContent).not.toContain('edit-auto')
  })
})
