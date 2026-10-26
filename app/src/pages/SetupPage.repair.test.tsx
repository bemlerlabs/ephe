// T2 — a start the stored key refused lands here, and the screen names the ways out.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts && typeof opts.engine === 'string' ? `${k}:${opts.engine}` : k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const updateSettings = vi.fn<(payload: unknown) => Promise<unknown>>(async () => ({}))
const storeEngineKey = vi.fn<(key: string) => Promise<void>>(async () => {})
const getSetupStatus = vi.fn()
const detectEngines = vi.fn(async () => ({ candidates: [], detected: [], first_reachable: -1 }))

vi.mock('@/lib/api', () => ({
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
  probeProvider: vi.fn(async () => ({ reachable: false, models: [], detail: '', state: 'unreachable' })),
  updateSettings: (payload: unknown) => updateSettings(payload),
  resetSetup: vi.fn(),
  skipSetup: vi.fn(),
}))

vi.mock('@/lib/engineKey', () => ({
  storeEngineKey: (key: string) => storeEngineKey(key),
}))

import SetupPage from './SetupPage'

const REPAIR = {
  code: 'engine_key_mismatch',
  problem:
    'The stored engine key is bound to openai_compatible/deepseek-chat @ https://api.example.invalid/v1, but the active engine is openai_compatible/another-model @ https://api.example.invalid/v1.',
  active: {
    provider: 'openai_compatible',
    model: 'another-model',
    url: 'https://api.example.invalid/v1',
  },
  bound: {
    provider: 'openai_compatible',
    model: 'deepseek-chat',
    url: 'https://api.example.invalid/v1',
  },
  key_source: 'file',
  choices: ['keep_bound_engine', 'replace_key', 'choose_provider', 'cancel'],
}

const STATUS = {
  configured: false,
  skipped: false,
  provider: 'openai_compatible',
  model: null,
  url: null,
  reachable: false,
  available_models: [] as string[],
  repair: REPAIR,
}

beforeEach(() => {
  updateSettings.mockClear()
  storeEngineKey.mockClear()
  getSetupStatus.mockReset()
})

describe('SetupPage engine-key repair (T2)', () => {
  it('names both engines and where the key came from', async () => {
    getSetupStatus.mockResolvedValue(STATUS)

    render(<SetupPage onDone={vi.fn()} />)

    await screen.findByTestId('setup-repair')
    expect(screen.getByTestId('setup-repair-active').textContent).toBe(
      'openai_compatible/another-model',
    )
    expect(screen.getByTestId('setup-repair-bound').textContent).toBe(
      'openai_compatible/deepseek-chat',
    )
    expect(screen.getByTestId('setup-repair-source').textContent).toBe('setup.repairSource.file')
  })

  it('keeps the key and restores the engine it is bound to', async () => {
    getSetupStatus.mockResolvedValue(STATUS)
    const onDone = vi.fn()

    render(<SetupPage onDone={onDone} />)

    fireEvent.click(await screen.findByTestId('setup-repair-keep'))

    await waitFor(() => expect(updateSettings).toHaveBeenCalledTimes(1))
    expect(updateSettings.mock.calls[0]?.[0]).toEqual({
      provider: {
        type: 'openai_compatible',
        model: 'deepseek-chat',
        endpoint: 'https://api.example.invalid/v1',
      },
    })
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('replaces the key for the engine the configuration names', async () => {
    getSetupStatus.mockResolvedValue(STATUS)
    const onDone = vi.fn()

    render(<SetupPage onDone={onDone} />)

    fireEvent.click(await screen.findByTestId('setup-repair-replace'))
    fireEvent.change(screen.getByTestId('setup-repair-key'), {
      target: { value: 'test-key-value' },
    })
    fireEvent.click(screen.getByTestId('setup-repair-save'))

    await waitFor(() => expect(updateSettings).toHaveBeenCalledTimes(1))
    expect(storeEngineKey).toHaveBeenCalledWith('test-key-value')
    expect(updateSettings.mock.calls[0]?.[0]).toEqual({
      provider: {
        type: 'openai_compatible',
        model: 'another-model',
        endpoint: 'https://api.example.invalid/v1',
        api_key: 'test-key-value',
      },
    })
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('cancels without touching the configuration', async () => {
    getSetupStatus.mockResolvedValue(STATUS)

    render(<SetupPage onDone={vi.fn()} />)

    fireEvent.click(await screen.findByTestId('setup-repair-cancel'))

    expect(screen.queryByTestId('setup-repair')).toBeNull()
    expect(updateSettings).not.toHaveBeenCalled()
    expect(storeEngineKey).not.toHaveBeenCalled()
  })

  it('shows no repair on a plain first start', async () => {
    getSetupStatus.mockResolvedValue({ ...STATUS, repair: null })

    render(<SetupPage onDone={vi.fn()} />)

    await waitFor(() => expect(getSetupStatus).toHaveBeenCalled())
    expect(screen.queryByTestId('setup-repair')).toBeNull()
  })
})
