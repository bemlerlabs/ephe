// T2 — a start the stored key refused lands here, and the screen says why.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) => (opts?.returnObjects ? [] : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const getSetupStatus = vi.fn<
  () => Promise<{
    configured: boolean
    skipped: boolean
    provider: string
    model: string | null
    url: string | null
    reachable: boolean
    available_models: string[]
    repair: { code: 'engine_key_mismatch'; detail: string } | null
  }>
>()
const detectEngines = vi.fn(async () => ({ candidates: [], detected: [], first_reachable: -1 }))

vi.mock('@/lib/api', () => ({
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
  probeProvider: vi.fn(),
  updateSettings: vi.fn(),
  resetSetup: vi.fn(),
  skipSetup: vi.fn(),
}))

import SetupPage from './SetupPage'

const STATUS = {
  configured: false,
  skipped: false,
  provider: 'openai_compatible',
  model: 'deepseek-chat',
  url: 'https://api.deepseek.com/v1',
  reachable: false,
  available_models: [] as string[],
}

beforeEach(() => {
  getSetupStatus.mockReset()
})

describe('SetupPage engine-key repair (T2)', () => {
  it('names the mismatch above the choice', async () => {
    getSetupStatus.mockResolvedValue({
      ...STATUS,
      repair: {
        code: 'engine_key_mismatch',
        detail: 'The stored engine key is bound to another engine.',
      },
    })

    render(<SetupPage onDone={vi.fn()} />)

    const banner = await screen.findByTestId('setup-repair')
    expect(banner.textContent).toBe('setup.repairEngineKeyMismatch')
  })

  it('shows no repair banner on a plain first start', async () => {
    getSetupStatus.mockResolvedValue({ ...STATUS, repair: null })

    render(<SetupPage onDone={vi.fn()} />)

    await waitFor(() => expect(getSetupStatus).toHaveBeenCalled())
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.queryByTestId('setup-repair')).toBeNull()
  })
})
