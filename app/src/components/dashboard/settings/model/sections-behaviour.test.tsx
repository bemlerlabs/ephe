// I6-3: the Behaviour area — the chat section of the register finally has its
// own place, and its select values show German text instead of identifiers.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { BehaviourSection } from './sections-behaviour'
import type { SettingsModel } from './types'
import type { DeepSection } from '@/types'

const sections = [
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
        hint: 'Zeigt die Denkphase des Modells als eigene Zeile.',
        hintEn: 'Shows the model reasoning as its own line.',
      },
      {
        key: 'chat.details_mode',
        type: 'select',
        label: 'Antwortprozess',
        labelEn: 'Response process',
        default: 'expanded',
        value: 'expanded',
        options: ['expanded', 'collapsed'],
        optionLabels: [
          { value: 'expanded', label: 'Ausgeklappt', labelEn: 'Expanded' },
          { value: 'collapsed', label: 'Eingeklappt', labelEn: 'Collapsed' },
        ],
      },
      {
        key: 'chat.stream_idle_seconds',
        type: 'number',
        label: 'Stream-Abbruch nach Stille (s)',
        labelEn: 'Abort stream after silence (s)',
        default: 60,
        value: 60,
        min: 10,
        max: 600,
        step: 1,
      },
    ],
  },
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

describe('BehaviourSection', () => {
  it('zeigt Titel, Zweck und jede chat-Zeile — nichts aus appearance', () => {
    render(<BehaviourSection model={model()} />)
    expect(screen.getByTestId('page-title').textContent).toBe('settings.behaviourTitle')
    expect(screen.getByTestId('page-subtitle').textContent).toBe('settings.behaviourHint')
    expect(screen.getByTestId('deep-row-chat.show_reasoning')).toBeTruthy()
    // details_mode has its own two-stage switch now, not a raw select row.
    expect(screen.getByTestId('details-mode-group')).toBeTruthy()
    expect(screen.queryByTestId('deep-row-chat.details_mode')).toBeNull()
    expect(screen.getByTestId('deep-row-chat.stream_idle_seconds')).toBeTruthy()
    expect(screen.queryByTestId('deep-row-appearance.font_scale')).toBeNull()
  })

  it('führt jede Zeile mit Beschreibungstext aus dem Register', () => {
    render(<BehaviourSection model={model()} />)
    expect(screen.getByTestId('deep-row-chat.show_reasoning-desc').textContent).toContain(
      'Denkphase',
    )
  })

  it('names the two stages instead of listing raw values', () => {
    render(<BehaviourSection model={model()} />)
    expect(screen.getByTestId('details-mode-collapsed')).toBeTruthy()
    expect(screen.getByTestId('details-mode-expanded')).toBeTruthy()
    expect(screen.queryByTestId('setting-select-chat.details_mode')).toBeNull()
  })

  it('schreibt eine Aenderung in den Draft', () => {
    const setDeepField = vi.fn()
    render(<BehaviourSection model={model({ setDeepField })} />)
    fireEvent.click(screen.getByTestId('details-mode-collapsed'))
    expect(setDeepField).toHaveBeenCalledWith('chat', 'chat.details_mode', 'collapsed')
    fireEvent.click(screen.getByTestId('setting-switch-chat.show_reasoning'))
    expect(setDeepField).toHaveBeenCalledWith('chat', 'chat.show_reasoning', false)
  })

  it('edits the custom instructions in a full-width card, not as a row', () => {
    const instructions = {
      key: 'chat.custom_instructions',
      type: 'text',
      label: 'Eigene Anweisungen',
      labelEn: 'Custom instructions',
      default: '',
      value: 'Be brief.',
      maxChars: 4000,
      multiline: true,
      hint: 'Stehende Vorgaben.',
      hintEn: 'Standing instructions.',
    }
    const withInstructions = [
      { key: 'chat', fields: [...sections[0]!.fields, instructions] },
    ] as unknown as DeepSection[]
    render(<BehaviourSection model={model({ deepSections: withInstructions })} />)
    const box = screen.getByTestId('custom-instructions-input') as HTMLTextAreaElement
    expect(box.value).toBe('Be brief.')
    expect(screen.getByTestId('custom-instructions-count').textContent).toBe('9 / 4000')
    // The register renders it once, in the card.
    expect(screen.queryByTestId('setting-text-chat.custom_instructions')).toBeNull()
  })

  it('stops typing at the cap from the register', () => {
    const setDeepField = vi.fn()
    const instructions = {
      key: 'chat.custom_instructions',
      type: 'text',
      label: 'Eigene Anweisungen',
      labelEn: 'Custom instructions',
      default: '',
      value: '',
      maxChars: 8,
      multiline: true,
    }
    const withInstructions = [
      { key: 'chat', fields: [...sections[0]!.fields, instructions] },
    ] as unknown as DeepSection[]
    render(<BehaviourSection model={model({ deepSections: withInstructions, setDeepField })} />)
    fireEvent.change(screen.getByTestId('custom-instructions-input'), {
      target: { value: '1234567890' },
    })
    expect(setDeepField).toHaveBeenCalledWith('chat', 'chat.custom_instructions', '12345678')
  })

  it('klemmt die Zahl an die Schranke aus dem Payload', () => {
    render(<BehaviourSection model={model()} />)
    const input = screen.getByTestId('setting-number-chat.stream_idle_seconds') as HTMLInputElement
    expect(input.min).toBe('10')
    expect(input.max).toBe('600')
    expect(input.step).toBe('1')
  })
})
