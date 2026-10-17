// I3-V5: the register block moves into the sections — here as its own test.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { DeepFields } from './deepFields'
import { deepFieldsOf } from './deepRegister'
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
        step: 1,
        hint: 'Setzt die Schriftgröße der Oberfläche.',
        hintEn: 'Sets the interface text size.',
      },
    ],
  },
  {
    key: 'chat',
    fields: [
      {
        key: 'chat.show_reasoning',
        type: 'bool',
        label: 'Denkprozess anzeigen',
        labelEn: 'Show reasoning',
        default: true,
        value: true,
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

describe('deepFieldsOf', () => {
  it('holt nur die angeforderten Sektionen', () => {
    expect(deepFieldsOf(sections, ['appearance.', 'chat.']).map((sec) => sec.key)).toEqual([
      'appearance',
      'chat',
    ])
    expect(deepFieldsOf(null, ['appearance.'])).toEqual([])
  })
})

describe('DeepFields im Bereich', () => {
  it('zeigt die Zeilen der eigenen Praefixe und laesst die anderen weg', () => {
    render(<DeepFields model={model()} prefixes={['appearance.', 'chat.']} />)
    expect(screen.getByTestId('deep-row-appearance.font_scale')).toBeTruthy()
    expect(screen.getByTestId('deep-row-chat.show_reasoning')).toBeTruthy()
    expect(screen.queryByTestId('deep-row-plugins.plugin_autorun')).toBeNull()
  })

  it('zeigt den Beschreibungstext nur, wenn das Feld einen hat', () => {
    render(<DeepFields model={model()} prefixes={['appearance.', 'chat.']} />)
    expect(screen.getByTestId('deep-row-appearance.font_scale-desc').textContent).toContain(
      'Schriftgröße',
    )
    expect(screen.queryByTestId('deep-row-chat.show_reasoning-desc')).toBeNull()
  })

  it('schreibt eine Aenderung in den Draft', () => {
    const setDeepField = vi.fn()
    render(<DeepFields model={model({ setDeepField })} prefixes={['appearance.', 'chat.']} />)
    fireEvent.click(screen.getByTestId('setting-switch-chat.show_reasoning'))
    expect(setDeepField).toHaveBeenCalledWith('chat', 'chat.show_reasoning', false)
  })

  // I6-1: the block has no button of its own any more — one button per section,
  // serving both storage areas, sits in the footer (SettingsPanel.save.test.tsx).
  it('hat weder eigenen Speichern-Knopf noch eigenen Zaehler', () => {
    render(
      <DeepFields
        model={model({ deepDraft: { chat: { 'chat.show_reasoning': false } } })}
        prefixes={['appearance.', 'chat.']}
      />,
    )
    expect(screen.queryByTestId('deep-save')).toBeNull()
    expect(screen.queryByTestId('deep-changed-count')).toBeNull()
  })

  it('verschwindet ganz, wenn das Register leer ist', () => {
    const { container } = render(
      <DeepFields model={model({ deepSections: null })} prefixes={['advanced.']} />,
    )
    expect(container.firstChild).toBeNull()
  })
})
