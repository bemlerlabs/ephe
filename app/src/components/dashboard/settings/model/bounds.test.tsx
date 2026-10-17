// I3-3: the range display and the clamping come from the payload, not from the TSX.
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import {
  clampDeepDraft,
  clampToBound,
  countDeepChanges,
  generationValues,
  rangeLabel,
} from './bounds'
import { renderGeneration } from './sections-generation'
import type { SettingsModel } from './types'
import type { DeepSection } from '@/types'

describe('clampToBound', () => {
  it('klemmt nach unten und oben', () => {
    expect(clampToBound(-5, { min: 0, max: 2 })).toBe(0)
    expect(clampToBound(5, { min: 0, max: 2 })).toBe(2)
    expect(clampToBound(1.5, { min: 0, max: 2 })).toBe(1.5)
  })

  it('laesst eine fehlende obere Schranke offen', () => {
    expect(clampToBound(999999, { min: 1, max: null })).toBe(999999)
  })

  it('ohne Grenzen bleibt der Wert, was auch immer er war', () => {
    expect(clampToBound(7, undefined)).toBe(7)
  })
})

describe('rangeLabel', () => {
  it('bildet den Text aus den Grenzen statt ihn zu kennen', () => {
    expect(rangeLabel({ min: 0, max: 2 })).toBe('0–2')
    expect(rangeLabel({ min: 1, max: null })).toBe('≥1')
    expect(rangeLabel(undefined)).toBe('')
  })
})

describe('generationValues', () => {
  const bounds = { temperature: { min: 0, max: 2 }, tool_budget: { min: 1, max: 40 } }

  it('uebernimmt nur gesetzte, gueltige Zahlen — geklemmt', () => {
    expect(
      generationValues(
        { temperature: '5', top_p: '', tool_budget: '0', junk: 'x' },
        ['temperature', 'top_p', 'tool_budget', 'junk'],
        bounds,
      ),
    ).toEqual({ temperature: 2, tool_budget: 1 })
  })

  it('ohne Grenzen im Payload geht der rohe Wert durch', () => {
    expect(generationValues({ temperature: '5' }, ['temperature'], undefined)).toEqual({
      temperature: 5,
    })
  })
})

describe('clampDeepDraft', () => {
  const sections = [
    {
      key: 'advanced',
      fields: [
        {
          key: 'advanced.api_timeout',
          type: 'number',
          label: 'API-Zeitüberschreitung (s)',
          labelEn: 'API timeout (s)',
          default: 120,
          value: 120,
          min: 10,
          max: 1800,
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
  ] as unknown as DeepSection[]

  it('klemmt Zahlfelder an die Register-Schranke', () => {
    const out = clampDeepDraft({ advanced: { 'advanced.api_timeout': 99999 } }, sections)
    expect(out.advanced?.['advanced.api_timeout']).toBe(1800)
  })

  it('laesst Bool, Leerfeld und Unbekanntes unberuehrt', () => {
    const out = clampDeepDraft(
      {
        advanced: { 'advanced.api_timeout': '' },
        appearance: { 'appearance.animations_enabled': true },
      },
      sections,
    )
    expect(out.advanced).toEqual({ 'advanced.api_timeout': '' })
  })

  it('ohne Register keine Veraenderung', () => {
    const draft = { advanced: { 'advanced.api_timeout': 99999 } }
    expect(clampDeepDraft(draft, null)).toBe(draft)
  })
})

describe('renderGeneration mit Meta aus dem Payload', () => {
  const model = {
    genDraft: { temperature: '' },
    setGenDraft: vi.fn(),
    i18n: { language: 'de' },
    t: (k: string) => k,
    settings: {
      provider: { type: 'local_ollama', model: 'gemma4:12b' },
      generation_meta: {
        temperature: {
          default: 0.7,
          min: 0,
          max: 1.5,
          hint: 'Wie zufällig die Wortwahl wird: 0 hält die Engine fest.',
          hintEn: 'How random the wording gets: 0 pins the engine.',
        },
        top_p: { default: null, min: 0, max: 1 },
        max_tokens: { default: null, min: 1, max: null },
        tool_budget: { default: 10, min: 1, max: 40 },
        context_window: { default: null, min: 1, max: null },
        memory_max_entries: { default: 1000, min: 1, max: null },
      },
    },
  } as unknown as SettingsModel

  it('zeigt die gelieferte Schranke, nicht die frueher getippte', () => {
    render(<div>{renderGeneration(model)}</div>)
    expect(screen.getByText('0–1.5')).toBeTruthy()
    expect(screen.queryByText('(0–2)')).toBeNull()
  })

  it('zeigt den Text des Hebels aus dem Payload', () => {
    render(<div>{renderGeneration(model)}</div>)
    expect(screen.getByTestId('generation-row-temperature-desc').textContent).toContain('Wortwahl')
  })

  it('setzt min/max am Input — die Native-Spinne kann nicht mehr hinauslaufen', () => {
    render(<div>{renderGeneration(model)}</div>)
    const input = screen.getByTestId('setting-number-temperature') as HTMLInputElement
    expect(input.min).toBe('0')
    expect(input.max).toBe('1.5')
  })

  it('zeigt jeden der sechs Hebel als eigene Zeile', () => {
    render(<div>{renderGeneration(model)}</div>)
    for (const key of [
      'temperature',
      'top_p',
      'max_tokens',
      'tool_budget',
      'context_window',
      'memory_max_entries',
    ]) {
      expect(screen.getByTestId(`generation-row-${key}`)).toBeTruthy()
    }
  })
})

// I6-1: the same yardstick decides whether the footer button writes to
// settings.json at all — and shows what has not arrived there yet.
describe('countDeepChanges', () => {
  const sections = [
    {
      key: 'appearance',
      fields: [
        { key: 'appearance.font_scale', type: 'number', default: 100, value: 100 },
        { key: 'appearance.animations_enabled', type: 'bool', default: true, value: true },
      ],
    },
    {
      key: 'chat',
      fields: [{ key: 'chat.show_reasoning', type: 'bool', default: true, value: true }],
    },
  ] as unknown as DeepSection[]

  it('ohne Draft und ohne Register bleibt es bei null', () => {
    expect(countDeepChanges(sections, {})).toBe(0)
    expect(countDeepChanges(null, { appearance: { 'appearance.font_scale': 120 } })).toBe(0)
  })

  it('zaehlt nur Abweichungen vom Registerwert, ueber alle Sektionen', () => {
    expect(countDeepChanges(sections, { appearance: { 'appearance.font_scale': 100 } })).toBe(0)
    expect(
      countDeepChanges(sections, {
        appearance: { 'appearance.font_scale': 120, 'appearance.animations_enabled': true },
        chat: { 'chat.show_reasoning': false },
      }),
    ).toBe(2)
  })

  it('ein geleertes Zahlenfeld ist keine Aenderung — es bleibt beim Registerwert', () => {
    expect(countDeepChanges(sections, { appearance: { 'appearance.font_scale': '' } })).toBe(0)
  })
})
