// R1 (WP7): the ephemerality section shows the two controls that really are read —
// and shows them in the language of the interface.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { EphemeraSection } from './sections-ephemera'
import type { SettingsModel } from './types'
import type { DeepSection } from '@/types'

const sections: DeepSection[] = [
  {
    key: 'ephemera',
    fields: [
      {
        key: 'ephemera.idle_ttl_minutes',
        type: 'number',
        default: 30,
        min: 5,
        max: 240,
        value: 30,
        label: 'Ungenutzte Zelle aufgeben (Minuten)',
        labelEn: 'Discard an idle cell (minutes)',
        hint: 'Wie lange eine Zelle ohne jeden Lauf überlebt; der nächste Zugriff räumt sie dann weg.',
        hintEn: 'How long a cell survives without a run; the next access then discards it.',
      },
      {
        key: 'ephemera.evaporate_on_delete',
        type: 'bool',
        default: false,
        value: false,
        label: 'Sitzung sofort verdunsten',
        labelEn: 'Evaporate session on delete',
        hint: 'Ob das Löschen einer Sitzung auch ihre Arbeitsmappe freigibt.',
        hintEn: 'Whether deleting a session also frees its work directory.',
      },
    ],
  },
] as unknown as DeepSection[]

function model(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    deepSections: sections,
    deepDraft: {},
    setDeepField: vi.fn(),
    ...over,
  } as unknown as SettingsModel
}

describe('EphemeraSection (R1)', () => {
  it('zeigt beide Regler mit ihrer eigenen Erklärung', () => {
    render(<EphemeraSection model={model()} />)
    expect(screen.getByTestId('deep-row-ephemera.idle_ttl_minutes')).toBeTruthy()
    expect(screen.getByTestId('deep-row-ephemera.evaporate_on_delete')).toBeTruthy()
    expect(screen.getByText(/nächste Zugriff räumt/)).toBeTruthy()
  })

  it('schreibt eine Änderung in den Entwurf des Bereichs, nicht irgendwohin', () => {
    const setDeepField = vi.fn()
    render(<EphemeraSection model={model({ setDeepField })} />)
    const input = screen.getByTestId('deep-row-ephemera.idle_ttl_minutes').querySelector('input')!
    fireEvent.change(input, { target: { value: '90' } })
    fireEvent.blur(input)
    expect(setDeepField).toHaveBeenCalledWith('ephemera', 'ephemera.idle_ttl_minutes', 90)
  })

  it('heisst die Gruppe nach dem Register, nicht nach ihrem Schlüssel', () => {
    render(<EphemeraSection model={model()} />)
    expect(screen.getByTestId('deep-section-ephemera').textContent).toContain(
      'settings.deepSection.ephemera',
    )
  })
})
