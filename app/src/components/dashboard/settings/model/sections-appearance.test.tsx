// I3-V5: the Appearance section — the register rows that were hidden in the expert box
// before it existed. The theme row and its toggle went with the paper ground (owner decision
// 2026-10-19: the forest is the only theme), and one test below keeps them from creeping back.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { AppearanceSection } from './sections-appearance'
import { COMPANION_KEYS } from './CompanionStudioCard'
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
        key: 'appearance.chat_font_scale',
        type: 'number',
        label: 'Schriftgröße im Gespräch (%)',
        labelEn: 'Chat font scale (%)',
        default: 100,
        value: 100,
        min: 80,
        max: 150,
      },
      {
        key: 'appearance.reading_width',
        type: 'number',
        label: 'Lesebreite (px)',
        labelEn: 'Reading width (px)',
        default: 768,
        value: 768,
        min: 480,
        max: 1200,
      },
      {
        key: 'appearance.companion_enabled',
        type: 'bool',
        label: 'Begleiter (Pet) im Arbeitsbereich',
        labelEn: 'Workspace companion (pet)',
        default: true,
        value: true,
      },
      {
        key: 'appearance.companion_species',
        type: 'select',
        label: 'Begleiter-Gestalt',
        labelEn: 'Companion form',
        default: 'fire_bee',
        value: 'fire_bee',
        options: ['fire_bee', 'ember_spark', 'minimal'],
      },
      {
        key: 'appearance.companion_behavior',
        type: 'select',
        label: 'Begleiter-Verhalten',
        labelEn: 'Companion behaviour',
        default: 'interactive',
        value: 'interactive',
        options: ['interactive', 'perch', 'header', 'welcome_only'],
      },
      {
        key: 'appearance.companion_sound',
        type: 'bool',
        label: 'Begleiter- & Funken-Klänge',
        labelEn: 'Companion & spark sounds',
        default: true,
        value: true,
      },
      {
        key: 'appearance.companion_scale',
        type: 'number',
        label: 'Begleiter-Größe (%)',
        labelEn: 'Companion size (%)',
        default: 100,
        value: 100,
        min: 70,
        max: 140,
      },
      {
        key: 'appearance.companion_mode',
        type: 'select',
        value: 'copilot',
        default: 'copilot',
        label: 'mode',
        labelEn: 'mode',
        options: ['perch', 'scout', 'copilot'],
      },
      {
        key: 'appearance.companion_countdown_seconds',
        type: 'number',
        value: 2.5,
        default: 2.5,
        min: 0,
        max: 10,
        step: 0.5,
        label: 'countdown',
        labelEn: 'countdown',
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
  it('zaehlt die Zeilen des Bereichs: die Appearance-Felder des Registers', () => {
    render(<AppearanceSection model={model()} />)
    expect(screen.getByTestId('deep-row-appearance.font_scale')).toBeTruthy()
    expect(screen.getByTestId('deep-row-appearance.animations_enabled')).toBeTruthy()
    // I6-3: the chat fields moved to Behaviour; plugin policy was never here.
    expect(screen.queryByTestId('deep-row-chat.details_mode')).toBeNull()
    expect(screen.queryByTestId('deep-row-plugins.plugin_autorun')).toBeNull()
  })

  it('a density preset writes only its two keys', () => {
    const setDeepField = vi.fn()
    render(<AppearanceSection model={model({ setDeepField })} />)
    fireEvent.click(screen.getByRole('radio', { name: 'settings.presetDensityCompact' }))
    expect(setDeepField).toHaveBeenCalledWith('appearance', 'appearance.font_scale', 90)
    expect(setDeepField).toHaveBeenCalledWith('appearance', 'appearance.chat_font_scale', 90)
    expect(setDeepField).toHaveBeenCalledTimes(2)
  })

  it('a reading preset does not move the type keys', () => {
    const setDeepField = vi.fn()
    render(<AppearanceSection model={model({ setDeepField })} />)
    fireEvent.click(screen.getByRole('radio', { name: 'settings.presetReadingWide' }))
    expect(setDeepField).toHaveBeenCalledWith('appearance', 'appearance.reading_width', 1024)
    expect(setDeepField).toHaveBeenCalledTimes(1)
  })

  it('a layout preset writes all three of its keys', () => {
    const setDeepField = vi.fn()
    render(<AppearanceSection model={model({ setDeepField })} />)
    fireEvent.click(screen.getByRole('radio', { name: 'settings.presetLayoutFocus' }))
    expect(setDeepField).toHaveBeenCalledWith('appearance', 'appearance.font_scale', 90)
    expect(setDeepField).toHaveBeenCalledWith('appearance', 'appearance.chat_font_scale', 90)
    expect(setDeepField).toHaveBeenCalledWith('appearance', 'appearance.reading_width', 640)
  })

  it('renders the live companion studio with every register row', () => {
    render(<AppearanceSection model={model()} />)
    const studio = screen.getByTestId('companion-studio')
    expect(studio.querySelector('.companion-actor')).toBeTruthy()
    for (const key of COMPANION_KEYS) {
      expect(screen.getAllByTestId(`deep-row-${key}`)).toHaveLength(1)
    }
  })

  it('previews the draft species and scale', () => {
    render(
      <AppearanceSection
        model={model({
          deepDraft: {
            appearance: {
              'appearance.companion_species': 'ember_spark',
              'appearance.companion_scale': 120,
            },
          },
        })}
      />,
    )
    const studio = screen.getByTestId('companion-studio')
    expect(studio.querySelector('.companion-spark-eyes')).toBeTruthy()
    const actor = studio.querySelector<HTMLElement>('.companion-actor')
    expect(actor?.style.getPropertyValue('--companion-scale')).toBe('1.2')
  })

  it('a manual value switches the affected preset to Custom', () => {
    render(
      <AppearanceSection
        model={model({
          deepDraft: {
            appearance: {
              'appearance.font_scale': 95,
              'appearance.chat_font_scale': 95,
              'appearance.reading_width': 768,
            },
          },
        })}
      />,
    )
    expect(screen.getByTestId('appearance-preset-density-custom')).toBeTruthy()
    expect(screen.queryByTestId('appearance-preset-reading-custom')).toBeNull()
    expect(screen.getByTestId('appearance-preset-layout-custom')).toBeTruthy()
  })

  it('haelt keinen Theme-Schalter mehr: der Wald ist der einzige Grund', () => {
    render(<AppearanceSection model={model()} />)
    expect(screen.queryByTestId('appearance-row-theme')).toBeNull()
    expect(screen.queryByTestId('appearance-theme-light')).toBeNull()
    expect(screen.queryByTestId('appearance-theme-dark')).toBeNull()
    expect(document.documentElement.classList.contains('light')).toBe(false)
  })
})
