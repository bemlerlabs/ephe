// F5b — a half-written engine env lands on this page instead of a 500.
//
// QA 2026-11-10 (VERIFY-REPORT.md, F5b): with `EPHE_MODEL_PROVIDER` set and the model
// variable missing, `GET /api/setup/status` answered 500 and the one screen that can
// repair the choice could not load. The route now answers 200 with
// `status: degraded`, `engine_unavailable: true` and the resolver's reason; this pins
// that the page renders that reason and still offers its picker.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string) => k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const getSetupStatus = vi.fn()
const detectEngines = vi.fn(async () => ({ candidates: [], detected: [], first_reachable: -1 }))

vi.mock('@/lib/api', () => ({
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
  probeProvider: vi.fn(async () => ({
    reachable: false,
    models: [],
    detail: '',
    state: 'unreachable',
  })),
  updateSettings: vi.fn(async () => ({})),
  resetSetup: vi.fn(),
  skipSetup: vi.fn(),
}))

vi.mock('@/lib/engineKey', () => ({ storeEngineKey: vi.fn(async () => {}) }))

import SetupPage from './SetupPage'

const STATUS = {
  status: 'degraded',
  engine_unavailable: true,
  configured: false,
  skipped: false,
  provider: 'openai_compatible',
  model: '',
  url: null,
  reachable: false,
  available_models: [] as string[],
  candidates: [],
  repair: null,
  problem: 'EPHE_MODEL_PROVIDER=openai_compatible is set, but EPHE_OPENAI_COMPAT_MODEL is missing.',
  hint: 'Run `ephe configure` and pick your engine.',
}

beforeEach(() => {
  getSetupStatus.mockReset()
  detectEngines.mockReset()
})

describe('SetupPage with an unusable engine config (F5b)', () => {
  it('renders the reason instead of dying on the status call', async () => {
    getSetupStatus.mockResolvedValue(STATUS)
    detectEngines.mockResolvedValue({ candidates: [], detected: [], first_reachable: -1 })

    render(<SetupPage onDone={vi.fn()} />)

    const banner = await screen.findByTestId('setup-engine-unavailable')
    expect(banner.textContent).toContain('setup.engineUnavailable')
    expect(screen.getByTestId('setup-engine-unavailable-problem').textContent).toBe(STATUS.problem)
    expect(banner.textContent).toContain('setup.engineUnavailableFix')
  })

  it('keeps the picker on screen — the way out is one choice away', async () => {
    getSetupStatus.mockResolvedValue(STATUS)
    detectEngines.mockResolvedValue({ candidates: [], detected: [], first_reachable: -1 })

    render(<SetupPage onDone={vi.fn()} />)

    await screen.findByTestId('setup-engine-unavailable')
    expect(screen.getByTestId('setup-one-click')).toBeTruthy()
  })

  it('shows no banner for a healthy status', async () => {
    getSetupStatus.mockResolvedValue({
      ...STATUS,
      status: 'ok',
      engine_unavailable: false,
      problem: '',
      hint: '',
      provider: 'local_ollama',
      candidates: [{ provider: 'local_ollama', url: null }],
    })

    render(<SetupPage onDone={vi.fn()} />)

    await screen.findByTestId('setup-one-click')
    expect(screen.queryByTestId('setup-engine-unavailable')).toBeNull()
  })
})
