// I3-V5: the new Appearance section — theme plus the register rows that
// were hidden in the expert box before.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { AppearanceSection } from './sections-appearance'
import type { SettingsModel } from './types'
import type { DeepSection } from '@/types'

const sections = [
  {
    key: 'appearance',
    fields: [
      {
        key: 'appearance.font_scale',
        type: 'number',
        label: 'Schriftgröße (%)',
        labelEn: 'Font scale (%)',
        default: 100,
        value: 100,
        min: 80,
        max: 150,
      },
      {
        key: 'appearance.animations_enabled',
        type: 'bool',
        label: 'Animationen aktiv',
        labelEn: 'Animations enabled',
        default: true,
        value: true,
      },
    ],
  },
  {
    key: 'chat',
    fields: [
      {
        key: 'chat.details_mode',
        type: 'select',
        label: 'Werkzeug-Details',
        labelEn: 'Tool details',
        default: 'expanded',
        value: 'expanded',
        options: ['expanded', 'collapsed'],
      },
    ],
  },
  {
    key: 'plugins',
    fields: [
      {
        key: 'plugins.plugin_autorun',
        type: 'bool',
        label: 'Plugins automatisch starten',
        labelEn: 'Autorun plugins',
        default: false,
        value: false,
      },
    ],
  },
] as unknown as DeepSection[]

function model(over: Record<string, unknown> = {}) {
  return {
    deepSections: sections,
    deepDraft: {},
    i18n: { language: 'de' },
    t: (k: string) => k,
    setDeepField: vi.fn(),
    ...over,
  } as unknown as SettingsModel
}

beforeEach(() => localStorage.clear())

describe('AppearanceSection', () => {
  it('zaehlt die Zeilen des Bereichs: Theme und die Appearance-Felder', () => {
    render(<AppearanceSection model={model()} />)
    expect(screen.getByTestId('appearance-row-theme')).toBeTruthy()
    expect(screen.getByTestId('deep-row-appearance.font_scale')).toBeTruthy()
    expect(screen.getByTestId('deep-row-appearance.animations_enabled')).toBeTruthy()
    // I6-3: the chat fields moved to Behaviour; plugin policy was never here.
    expect(screen.queryByTestId('deep-row-chat.details_mode')).toBeNull()
    expect(screen.queryByTestId('deep-row-plugins.plugin_autorun')).toBeNull()
  })

  it('schaltet das Theme und speichert die Wahl im Gerat', () => {
    render(<AppearanceSection model={model()} />)
    const light = screen.getByTestId('appearance-theme-light')
    fireEvent.click(light)
    expect(light.getAttribute('aria-checked')).toBe('true')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(localStorage.getItem('ephe.theme')).toBe('light')
    fireEvent.click(screen.getByTestId('appearance-theme-dark'))
    expect(document.documentElement.classList.contains('light')).toBe(false)
  })
})
