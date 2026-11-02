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
  'chat.modeHint.ask': 'Ask — Ephe only answers, no tools run',
  'chat.modeHint.plan': 'Plan — Ephe drafts a plan first; nothing runs until you confirm',
  'chat.modeHint.edit-auto': 'Edit auto — the write tools run without asking, the rest still asks',
  'chat.modeHint.full-access': 'Full access — every tool runs without asking',
  'chat.perm.strict': 'Manual',
}

const DE: Record<string, string> = {
  'chat.modeSelectorAria': 'Antwort-Modus des Composers', // language-gate: ignore
  'chat.modeHint.ask': 'Fragen — Ephe antwortet nur, keine Werkzeuge laufen', // language-gate: ignore
  'chat.modeHint.plan':
    'Planen — Ephe entwirft erst einen Plan; nichts läuft ohne deine Bestätigung', // language-gate: ignore
  'chat.modeHint.edit-auto':
    'Bearbeiten — die Schreib-Werkzeuge laufen ohne Rückfrage, die übrigen nicht', // language-gate: ignore
  'chat.modeHint.full-access': 'Voller Zugriff — jedes Werkzeug läuft ohne Rückfrage', // language-gate: ignore
  'chat.perm.strict': 'Manuell', // language-gate: ignore
}

/** The four modes, in the order the menu lists them. */
const MODES = ['ask', 'plan', 'edit-auto', 'full-access'] as const

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
    renderChip('full-access')
    const chip = screen.getByTestId('composer-mode-selector')
    const profileWord = catalog['chat.perm.strict']!
    // The profile has its own chip; naming it here is the contradiction the finding saw.
    expect(chip.textContent).not.toContain(profileWord)
    expect(chip.getAttribute('aria-label')).not.toContain(profileWord)
    // The visible text is the mode alone — no word over it that names a different setting.
    expect(chip.textContent, 'the chip shows the mode and nothing else').toBe(
      shortLabel(catalog, 'full-access'),
    )
  })
})
