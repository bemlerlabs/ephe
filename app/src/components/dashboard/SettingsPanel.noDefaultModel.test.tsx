// D3 (#67 follow-on, from the weak-default sweep): the register surface must never name a
// model on the user's behalf. A read that failed, an engine that did not answer, and a save
// with nothing chosen each used to end in a shipped tag reaching the wire.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'

const { api, toastError, toastSuccess } = vi.hoisted(() => {
  const api = {
    getSettings: vi.fn(async () => ({
      provider: { type: 'local_ollama', model: '' },
      memory_enabled: true,
      language: 'de',
      theme: 'dark',
      workspace_dir: '',
      output_dir: '',
    })),
    updateSettings: vi.fn(async () => ({})),
    saveSections: vi.fn(async () => ({})),
    healthCheck: vi.fn(async () => ({
      status: 'ok',
      active_model: '',
      active_provider: 'local_ollama',
      engine_state: 'ok',
    })),
    getModelProviders: vi.fn<() => Promise<unknown>>(async () => ({
      active: {},
      providers: [],
      local_models: [],
      local_model_options: [],
    })),
    getMemoryStats: vi.fn(async () => ({ total: 0 })),
    listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
    getPackIndex: vi.fn(async () => ({ packs: [] })),
    listSchedules: vi.fn(async () => ({ jobs: [] })),
    getTasks: vi.fn(async () => []),
    getSecuritySettings: vi.fn(async () => ({
      approval_profile: 'strict',
      sandbox_enabled: false,
    })),
    saveSecuritySettings: vi.fn(async () => ({
      approval_profile: 'strict',
      sandbox_enabled: false,
    })),
  }
  return { api, toastError: vi.fn(), toastSuccess: vi.fn() }
})

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts?.returnObjects ? [] : opts ? `${k} ${JSON.stringify(opts)}` : k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

vi.mock('@/lib/toast', () => ({
  toastBus: { info: vi.fn(), error: toastError, success: toastSuccess },
  toast: { info: vi.fn(), error: toastError, success: toastSuccess },
}))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  ...api,
}))

import SettingsPanel from './SettingsPanel'

/** The main-block payload the footer sent. The mock keeps no argument type of its own. */
function saved(): Record<string, unknown> {
  const calls = api.updateSettings.mock.calls as unknown as Array<[Record<string, unknown>]>
  expect(calls.length, 'updateSettings never ran').toBe(1)
  return (calls[0] as [Record<string, unknown>])[0]
}

async function openEngine() {
  render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
  await screen.findByTestId('engine-group-model')
}

beforeEach(() => {
  localStorage.clear()
  toastError.mockClear()
  toastSuccess.mockClear()
  api.getSettings.mockClear()
  api.updateSettings.mockClear()
})

/** S2 host 2: the engine area's list became the shared picker, so a row with a
 *  `engine-row-model-*` anchor exists only for a model the user chose by hand. */
describe('the engine area chooses through the picker', () => {
  async function withThreeModels() {
    api.getModelProviders.mockResolvedValueOnce({
      active: {},
      providers: [],
      local_models: ['m1', 'm2', 'm3'],
      local_model_options: [
        { name: 'm1', label: 'm1', context_window: 131072, supports_tools: true, is_free: false },
        { name: 'm2', label: 'm2', context_window: null, supports_tools: null, is_free: null },
        { name: 'm3', label: 'm3', context_window: 8192, supports_tools: false, is_free: true },
      ],
    })
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    await screen.findByTestId('engine-group-model')
  }

  it('lists every model once and marks none as chosen', async () => {
    await withThreeModels()
    const rows = Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid^="engine-matrix-m"]'),
    ).filter((row) => /^engine-matrix-m\d+$/.test(row.getAttribute('data-testid') ?? ''))
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'engine-matrix-m1',
      'engine-matrix-m2',
      'engine-matrix-m3',
    ])
    for (const tag of ['m1', 'm2', 'm3']) {
      expect(screen.queryByTestId(`engine-matrix-inuse-${tag}`), tag).toBeNull()
    }
  })

  it('writes only the model whose Use was pressed, and only on save', async () => {
    await withThreeModels()
    const row = await screen.findByTestId('engine-matrix-m2')
    expect(row.textContent).toContain('m2')
    // A row is not a choice: nothing reaches the wire until Use, and the write
    // itself is the save at the bottom of the panel.
    expect(api.updateSettings).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('engine-matrix-use-m2'))
    await act(async () => {
      fireEvent.click(screen.getByTestId('settings-save'))
    })
    expect(saved().provider).toMatchObject({ model: 'm2' })
  })

  it('says what a stated no from the engine means on the row', async () => {
    // S3 capability messaging: m3 answers and refuses the tool array, and the row
    // the model sits on is where the surface has to say that.
    await withThreeModels()
    const shown = await screen.findByTestId('engine-matrix-m3')
    expect(shown.textContent).toContain('modelPicker.answerOnly')
  })

  it('keeps the row silent about tools for a model the engine described as able', async () => {
    await withThreeModels()
    const shown = await screen.findByTestId('engine-matrix-m1')
    expect(shown.textContent).not.toContain('modelPicker.answerOnly')
  })
})

describe('the register names no model the user did not choose', () => {
  it('offers only the free-text entry when the engine reported no list', async () => {
    await openEngine()
    for (const tag of ['gemma4:12b', 'llama3.1:8b', 'mistral:7b', 'gemma4:e4b']) {
      expect(screen.queryByTestId(`engine-row-model-${tag}`)).toBeNull()
    }
    expect(screen.getByTestId('engine-model-custom')).toBeTruthy()
  })

  it('sends no provider block when nothing is chosen, and says the model is missing', async () => {
    await openEngine()
    await act(async () => {
      fireEvent.click(screen.getByTestId('settings-save'))
    })
    const payload = saved()
    expect(payload.provider).toBeUndefined()
    expect(JSON.stringify(payload)).not.toContain('gemma4')
    expect(toastError).toHaveBeenCalledWith('settings.chooseModel', 'settings.modelListHint')
    expect(toastSuccess).not.toHaveBeenCalled()
  })

  it('cannot invent a tag out of a settings read that failed', async () => {
    api.getSettings.mockRejectedValueOnce(new Error('backend offline'))
    await openEngine()
    await act(async () => {
      fireEvent.click(screen.getByTestId('settings-save'))
    })
    const payload = saved()
    expect(payload.provider).toBeUndefined()
    expect(JSON.stringify(payload)).not.toContain('gemma4:e4b')
  })

  it('still saves the tag the user chose, unchanged', async () => {
    api.getSettings.mockResolvedValueOnce({
      provider: { type: 'local_ollama', model: 'mine:work' },
      memory_enabled: true,
      language: 'de',
      theme: 'dark',
      workspace_dir: '',
      output_dir: '',
    })
    await openEngine()
    await act(async () => {
      fireEvent.click(screen.getByTestId('settings-save'))
    })
    const payload = saved()
    expect((payload.provider as { model: string }).model).toBe('mine:work')
    expect(toastSuccess).toHaveBeenCalled()
  })

  it('keeps the folders and the language writable while the engine has no model', async () => {
    await openEngine()
    await act(async () => {
      fireEvent.click(screen.getByTestId('settings-save'))
    })
    const payload = saved()
    expect(payload).toHaveProperty('language')
    expect(payload).toHaveProperty('workspace_dir')
    expect(payload).toHaveProperty('memory_enabled')
  })
})
