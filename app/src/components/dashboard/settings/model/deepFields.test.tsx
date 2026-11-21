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

const solSections = [
  {
    key: 'sol',
    fields: [
      {
        key: 'sol.enabled',
        type: 'bool',
        label: 'Aus Fehlern lernen',
        labelEn: 'Learn from failures',
        default: true,
        value: true,
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
  it('fetches only the requested sections', () => {
    expect(deepFieldsOf(sections, ['appearance.', 'chat.']).map((sec) => sec.key)).toEqual([
      'appearance',
      'chat',
    ])
    expect(deepFieldsOf(null, ['appearance.'])).toEqual([])
  })
})

describe('DeepFields inside the area', () => {
  it('shows the rows of its own prefixes and leaves the others away', () => {
    render(<DeepFields model={model()} prefixes={['appearance.', 'chat.']} />)
    expect(screen.getByTestId('deep-row-appearance.font_scale')).toBeTruthy()
    expect(screen.getByTestId('deep-row-chat.show_reasoning')).toBeTruthy()
    expect(screen.queryByTestId('deep-row-plugins.plugin_autorun')).toBeNull()
  })

  it('shows the description text only when the field has one', () => {
    render(<DeepFields model={model()} prefixes={['appearance.', 'chat.']} />)
    expect(screen.getByTestId('deep-row-appearance.font_scale-desc').textContent).toContain(
      'Schriftgröße',
    )
    expect(screen.queryByTestId('deep-row-chat.show_reasoning-desc')).toBeNull()
  })

  it('writes a change into the draft', () => {
    const setDeepField = vi.fn()
    render(<DeepFields model={model({ setDeepField })} prefixes={['appearance.', 'chat.']} />)
    fireEvent.click(screen.getByTestId('setting-switch-chat.show_reasoning'))
    expect(setDeepField).toHaveBeenCalledWith('chat', 'chat.show_reasoning', false)
  })

  // I6-1: the block has no button of its own any more — one button per section,
  // serving both storage areas, sits in the footer (SettingsPanel.save.test.tsx).
  it('has neither its own save button nor its own counter', () => {
    render(
      <DeepFields
        model={model({ deepDraft: { chat: { 'chat.show_reasoning': false } } })}
        prefixes={['appearance.', 'chat.']}
      />,
    )
    expect(screen.queryByTestId('deep-save')).toBeNull()
    expect(screen.queryByTestId('deep-changed-count')).toBeNull()
  })

  it('disappears entirely when the register is empty', () => {
    const { container } = render(
      <DeepFields model={model({ deepSections: null })} prefixes={['advanced.']} />,
    )
    expect(container.firstChild).toBeNull()
  })
})

describe('DeepFields locale keys', () => {
  it('takes label and hint from the locale when the field carries a key', () => {
    const withKey = [
      {
        key: 'plugins',
        fields: [
          {
            key: 'plugins.plugin_lifecycle_read_only',
            type: 'bool',
            label: 'Plugin switches read-only',
            labelEn: 'Plugin switches read-only',
            labelKey: 'settings.pluginReadOnly',
            hintKey: 'settings.pluginReadOnlyHint',
            default: false,
            value: false,
          },
        ],
      },
    ] as unknown as DeepSection[]
    const t = (key: string) =>
      key === 'settings.pluginReadOnly'
        ? 'Read-only'
        : key === 'settings.pluginReadOnlyHint'
          ? 'Blocks switch changes.'
          : key

    render(<DeepFields model={model({ deepSections: withKey, t })} prefixes={['plugins.']} />)

    const row = screen.getByTestId('deep-row-plugins.plugin_lifecycle_read_only')
    expect(row.textContent).toContain('Read-only')
    expect(
      screen.getByTestId('deep-row-plugins.plugin_lifecycle_read_only-desc').textContent,
    ).toContain('Blocks switch changes.')
  })
})

describe('the SOL section from the register', () => {
  it('renders its own group with a header glyph and its row', () => {
    // The section key comes from core/settings_schema.py, so the icon map has to
    // know it before a backend ever answers — an unmapped header renders nothing.
    render(<DeepFields model={model({ deepSections: solSections })} prefixes={['sol.']} />)
    expect(screen.getByTestId('deep-fields')).toBeTruthy()
    expect(screen.getByTestId('deep-row-sol.enabled')).toBeTruthy()
    expect(screen.getByText('settings.deepSection.sol')).toBeTruthy()
  })
})
