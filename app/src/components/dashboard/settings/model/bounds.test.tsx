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
  it('clamps at the bottom and the top', () => {
    expect(clampToBound(-5, { min: 0, max: 2 })).toBe(0)
    expect(clampToBound(5, { min: 0, max: 2 })).toBe(2)
    expect(clampToBound(1.5, { min: 0, max: 2 })).toBe(1.5)
  })

  it('leaves a missing upper bound open', () => {
    expect(clampToBound(999999, { min: 1, max: null })).toBe(999999)
  })

  it('without bounds the value stays whatever it was', () => {
    expect(clampToBound(7, undefined)).toBe(7)
  })
})

describe('rangeLabel', () => {
  it('forms the label from the bounds and never from a memorised string', () => {
    expect(rangeLabel({ min: 0, max: 2 })).toBe('0–2')
    expect(rangeLabel({ min: 1, max: null })).toBe('≥1')
    expect(rangeLabel(undefined)).toBe('')
  })
})

describe('generationValues', () => {
  const bounds = { temperature: { min: 0, max: 2 }, tool_budget: { min: 1, max: 40 } }

  it('takes only set, valid numbers, clamped', () => {
    expect(
      generationValues(
        { temperature: '5', top_p: '', tool_budget: '0', junk: 'x' },
        ['temperature', 'top_p', 'tool_budget', 'junk'],
        bounds,
      ),
    ).toEqual({ temperature: 2, tool_budget: 1 })
  })

  it('without bounds in the payload the raw value passes through', () => {
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

  it('clamps number fields to the register bound', () => {
    const out = clampDeepDraft({ advanced: { 'advanced.api_timeout': 99999 } }, sections)
    expect(out.advanced?.['advanced.api_timeout']).toBe(1800)
  })

  it('leaves bool, empty field and the unknown untouched', () => {
    const out = clampDeepDraft(
      {
        advanced: { 'advanced.api_timeout': '' },
        appearance: { 'appearance.animations_enabled': true },
      },
      sections,
    )
    expect(out.advanced).toEqual({ 'advanced.api_timeout': '' })
  })

  it('without the register nothing changes', () => {
    const draft = { advanced: { 'advanced.api_timeout': 99999 } }
    expect(clampDeepDraft(draft, null)).toBe(draft)
  })
})

describe('renderGeneration with meta from the payload', () => {
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

  it('shows the delivered bound over one typed earlier', () => {
    render(<div>{renderGeneration(model)}</div>)
    expect(screen.getByText('0–1.5')).toBeTruthy()
    expect(screen.queryByText('(0–2)')).toBeNull()
  })

  it('shows the slider text from the payload', () => {
    render(<div>{renderGeneration(model)}</div>)
    expect(screen.getByTestId('generation-row-temperature-desc').textContent).toContain('Wortwahl')
  })

  it('sets min/max on the input so the native spinner cannot run away', () => {
    render(<div>{renderGeneration(model)}</div>)
    const input = screen.getByTestId('setting-number-temperature') as HTMLInputElement
    expect(input.min).toBe('0')
    expect(input.max).toBe('1.5')
  })

  it('shows each of the seven sliders as its own row', () => {
    render(<div>{renderGeneration(model)}</div>)
    for (const key of [
      'temperature',
      'top_p',
      'max_tokens',
      'tool_budget',
      'context_window',
      'memory_max_entries',
      'swarm_max_parallel',
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

  it('without a draft and a register it stays at zero', () => {
    expect(countDeepChanges(sections, {})).toBe(0)
    expect(countDeepChanges(null, { appearance: { 'appearance.font_scale': 120 } })).toBe(0)
  })

  it('counts only deviations from the register value, across all sections', () => {
    expect(countDeepChanges(sections, { appearance: { 'appearance.font_scale': 100 } })).toBe(0)
    expect(
      countDeepChanges(sections, {
        appearance: { 'appearance.font_scale': 120, 'appearance.animations_enabled': true },
        chat: { 'chat.show_reasoning': false },
      }),
    ).toBe(2)
  })

  it('an emptied number field is no change; it stays at the register value', () => {
    expect(countDeepChanges(sections, { appearance: { 'appearance.font_scale': '' } })).toBe(0)
  })
})
