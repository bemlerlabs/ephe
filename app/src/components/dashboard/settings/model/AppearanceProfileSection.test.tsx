import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { DeepField } from '@/types'
import type { SettingsModel } from './types'
import { AppearanceProfile } from './AppearanceProfileSection'

const FIELDS: DeepField[] = [
  {
    key: 'appearance.accent',
    type: 'select',
    label: 'Akzent',
    labelEn: 'Accent',
    default: 'ember',
    value: 'ember',
    options: ['ember', 'indigo', 'plum', 'mono'],
  },
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
]

function model(save = vi.fn(async () => ({ ok: true }))) {
  return {
    t: (key: string) => key,
    deepSections: [{ key: 'appearance', fields: FIELDS }],
    deepDraft: { appearance: { 'appearance.accent': 'indigo', 'appearance.font_scale': 100 } },
    saveAppearanceProfile: save,
  } as unknown as SettingsModel
}

const createObjectURL = vi.fn(() => 'blob:profile')
const revokeObjectURL = vi.fn()

beforeEach(() => {
  Object.assign(URL, { createObjectURL, revokeObjectURL })
  vi.clearAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('appearance profile rows', () => {
  it('offers export, import and reset', () => {
    render(<AppearanceProfile model={model()} />)
    expect(screen.getByTestId('appearance-profile-export')).toBeTruthy()
    expect(screen.getByTestId('appearance-profile-import')).toBeTruthy()
    expect(screen.getByTestId('appearance-profile-reset')).toBeTruthy()
  })

  it('resets every appearance default in one write', async () => {
    const save = vi.fn(async () => ({ ok: true }))
    render(<AppearanceProfile model={model(save)} />)
    fireEvent.click(screen.getByTestId('appearance-profile-reset-btn'))
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith({
        'appearance.accent': 'ember',
        'appearance.font_scale': 100,
      }),
    )
    expect(screen.getByTestId('appearance-profile-status').textContent).toBe(
      'settings.appearanceProfileApplied',
    )
  })

  it('applies a valid imported file', async () => {
    const save = vi.fn(async () => ({ ok: true }))
    render(<AppearanceProfile model={model(save)} />)
    const file = new File(
      [JSON.stringify({ ephe_appearance: 1, values: { 'appearance.accent': 'plum' } })],
      'profile.json',
      { type: 'application/json' },
    )
    fireEvent.change(screen.getByTestId('appearance-profile-file'), {
      target: { files: [file] },
    })
    await waitFor(() => expect(save).toHaveBeenCalledWith({ 'appearance.accent': 'plum' }))
  })

  it('names the refusal reason and writes nothing', async () => {
    const save = vi.fn(async () => ({ ok: true }))
    render(<AppearanceProfile model={model(save)} />)
    const file = new File(
      [JSON.stringify({ ephe_appearance: 1, values: { 'appearance.font_scale': 999 } })],
      'profile.json',
      { type: 'application/json' },
    )
    fireEvent.change(screen.getByTestId('appearance-profile-file'), {
      target: { files: [file] },
    })
    await waitFor(() =>
      expect(screen.getByTestId('appearance-profile-status').textContent).toBe(
        'settings.appearanceProfileOutOfRange',
      ),
    )
    expect(save).not.toHaveBeenCalled()
  })

  it('exports one JSON file and reports it', () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<AppearanceProfile model={model()} />)
    fireEvent.click(screen.getByTestId('appearance-profile-export-btn'))
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('appearance-profile-status').textContent).toBe(
      'settings.appearanceProfileExported',
    )
  })
})
