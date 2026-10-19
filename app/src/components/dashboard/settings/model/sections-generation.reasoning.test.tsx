// Wave 2/B4: the engine's reasoning-effort option in the generation card. Unset is
// the first choice and the one every earlier version sent; a chosen value shows.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { renderGeneration } from './sections-generation'
import type { SettingsModel } from './types'

function generationModel(over: Record<string, unknown> = {}) {
  const setGenDraft = vi.fn()
  const model = {
    genDraft: {},
    i18n: { language: 'en' },
    setGenDraft,
    settings: {
      generation: {},
      generation_meta: { temperature: { default: 0, min: 0, max: 2 } },
    },
    t: (key: string) => key,
    ...over,
  } as unknown as SettingsModel
  return { model, setGenDraft }
}

describe('the reasoning-effort row', () => {
  it('offers the engine default first and the engine vocabulary after it', () => {
    const { model } = generationModel()
    render(<>{renderGeneration(model)}</>)
    const select = screen.getByTestId('generation-reasoning-effort') as HTMLSelectElement
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      '',
      'none',
      'low',
      'medium',
      'high',
    ])
    expect(select.options[0]?.textContent).toBe('settings.genReasoningUnset')
  })

  it('shows the stored value', () => {
    const { model } = generationModel({
      genDraft: { reasoning_effort: 'medium' },
    })
    render(<>{renderGeneration(model)}</>)
    const select = screen.getByTestId('generation-reasoning-effort') as HTMLSelectElement
    expect(select.value).toBe('medium')
  })

  it('writes the choice into the generation draft', () => {
    const { model, setGenDraft } = generationModel()
    render(<>{renderGeneration(model)}</>)
    fireEvent.change(screen.getByTestId('generation-reasoning-effort'), {
      target: { value: 'low' },
    })
    expect(setGenDraft).toHaveBeenCalled()
    const updater = (setGenDraft.mock.calls[0] as unknown as [(p: object) => object])[0]
    expect(updater({ temperature: '0.2' })).toEqual({
      temperature: '0.2',
      reasoning_effort: 'low',
    })
  })
})
