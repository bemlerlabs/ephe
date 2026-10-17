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
    getModelProviders: vi.fn(async () => ({
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
