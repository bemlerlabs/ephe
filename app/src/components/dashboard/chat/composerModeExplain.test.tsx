/**
 * The mode menu has to say what a mode does, inside the interface.
 *
 * Walkthrough 2026-10-12 (medium): the open menu listed the four bare short
 * labels under `WITHOUT TOOLS | READ ONLY | WITH WRITE ACCESS`, and the sentence
 * that says what a mode does lived in a native `title` alone — so a reader who
 * did not hover learned nothing from the product about its widest-reaching
 * control. The aria-label repeated the short label before the sentence
 * ("Plan — Plan — Ephe drafts a plan first; …"), so a screen reader heard the
 * name twice.
 *
 * Held here, in English, against the shipped bundle: every row carries its
 * sentence as visible text, the accessible name is that sentence once, and the
 * menu names the second store (the approval profile) and which of the two is the
 * ceiling.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useRef } from 'react'
import en from '@/locales/en.json'

const HINTS = (en as unknown as { chat: { modeHint: Record<string, string> } }).chat.modeHint
/** The sentence after the em dash — the half that was hover-only. */
const meaning = (key: string): string =>
  String(HINTS[key] ?? '')
    .split('—')
    .slice(1)
    .join('—')
    .trim()

vi.mock('react-i18next', async () => {
  const bundle = (await import('@/locales/en.json')).default as Record<string, unknown>
  const read = (key: string): string | undefined => {
    let node: unknown = bundle
    for (const part of key.split('.')) {
      if (typeof node !== 'object' || node === null) return undefined
      node = (node as Record<string, unknown>)[part]
    }
    return typeof node === 'string' ? node : undefined
  }
  return {
    initReactI18next: { type: '3rdParty', init: () => undefined },
    useTranslation: () => ({
      i18n: { language: 'en' },
      t: (key: string, opts?: { defaultValue?: string }) => read(key) ?? opts?.defaultValue ?? key,
    }),
  }
})

import ComposerModeChip from './ComposerModeChip'
import { COMPOSER_MODES } from './ComposerModeMenu'

const KEYS = COMPOSER_MODES.map((m) => [m.key] as const)

function OpenMenu({ mode }: { mode: string }) {
  const ref = useRef<HTMLButtonElement>(null)
  return (
    <ComposerModeChip
      open
      approval="strict"
        mode={mode}
      anchorRef={ref}
      menuPos={{ left: 120, bottom: 120 }}
      onToggle={() => undefined}
      onClose={() => undefined}
      onPick={() => undefined}
    />
  )
}

describe('the composer mode menu', () => {
  it.each(KEYS)('%s shows its sentence without a hover', (key) => {
    render(<OpenMenu mode={key} />)
    const row = screen.getByTestId(`composer-mode-${key}`)
    expect(row.textContent).toContain(meaning(key))
    expect(meaning(key).length).toBeGreaterThan(10)
  })

  it.each(KEYS)('%s names the mode exactly once for a screen reader', (key) => {
    render(<OpenMenu mode={key} />)
    const row = screen.getByTestId(`composer-mode-${key}`)
    const label = row.getAttribute('aria-label') ?? ''
    // The whole sentence, and the em dash that separates it from the label only once.
    expect(label).toBe(HINTS[key])
    expect(label.split('—').length - 1).toBe(1)
  })

  it('says what each surface decides and which one is the ceiling', () => {
    render(<OpenMenu mode="plan" />)
    const note = screen.getByTestId('composer-mode-note')
    expect(note.textContent).toContain('approval profile')
    expect(note.textContent).toContain('mode')
  })
})
