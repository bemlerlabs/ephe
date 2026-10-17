// W18/A5 — Engine tab: the active engine stays visible and its connection test
// separates the three states ok | busy | unreachable (busy = the engine
// answers slowly, NOT offline). Source: GET /api/health (engine_state).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    // t returns the key; interpolation values get appended, so that tests
    // can see the engine data passed through (provider/URL).
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts?.returnObjects ? [] : opts ? `${k} ${JSON.stringify(opts)}` : k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

type HealthInfo = import('@/lib/api').HealthInfo

const healthCheck = vi.fn(async (): Promise<HealthInfo> => ({
  status: 'ok',
  ollama: false,
  models: [],
  active_tier: 'power',
  active_model: 'my-served-model',
  dgx_online: true,
  active_provider: 'openai_compatible',
  offline_capable: false,
  requires_internet: true,
  engine_online: true,
  engine_state: 'ok',
}))

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({
    provider: {
      type: 'openai_compatible',
      model: 'my-served-model',
      endpoint: 'http://10.1.2.3:8000/v1',
    },
    memory_enabled: true,
    language: 'de',
    theme: 'dark',
  })),
  updateSettings: vi.fn(async () => ({})),
  healthCheck: () => healthCheck(),
  getModelProviders: vi.fn(async () => ({
    active: {},
    providers: [],
    local_models: [],
    local_model_options: [],
  })),
  getMemoryStats: vi.fn(async () => ({ total: 0 })),
  clearMemory: vi.fn(async () => ({ cleared: true })),
  getMobileQR: vi.fn(async () => ({
    url: '',
    qr_base64: '',
    mode: 'lan',
    is_public: false,
    requires_internet: false,
    lan_reachable: true,
    message: '',
  })),
  getMobileStatus: vi.fn(async () => ({ connected: false })),
  listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
  getImageSettings: vi.fn(async () => ({
    base_url: '',
    model: '',
    has_api_key: false,
    api_key_hint: '',
  })),
  saveImageSettings: vi.fn(async () => ({
    base_url: '',
    model: '',
    has_api_key: false,
    api_key_hint: '',
  })),
  testImageEndpoint: vi.fn(async () => ({
    reachable: false,
    models: [],
    base_url_used: '',
    detail: '',
  })),
  getSchedulePresets: vi.fn(async () => ({ presets: [] })),
  getScheduleResults: vi.fn(async () => ({ results: [] })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  getTasks: vi.fn(async () => []),
  fileUrl: (p: string) => p,
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
  getSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  saveSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
}))

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  localStorage.clear()
  healthCheck.mockClear()
})

describe('SettingsPanel Engine-Tab (W18/A5)', () => {
  it('zeigt die aktive Engine (Provider · Modell-Ziel-URL) sichtbar an', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)

    const box = await screen.findByTestId('settings-active-engine')
    // Engine choice stays visible (no hidden default): provider + endpoint.
    // The provider is named by its **name**, not as an identifier: the line
    // under the title used to carry `openai_compatible` while the title had long
    // said „OpenAI-kompatible API" — the same information, once in German. // language-gate: ignore (quoted UI label, app/src/locales/de.json:861)
    await waitFor(() => expect(box.textContent).toContain('10.1.2.3:8000/v1'))
    expect(box.textContent).toContain('settings.providerLabelOpenAiCompat')
    expect(box.textContent).not.toContain('openai_compatible')
    expect(box.textContent).toContain('settings.activeEngine')
    expect(screen.getByTestId('settings-engine-test')).toBeInTheDocument()
  })

  it('Verbindungstest zeigt ok aus der Health-Probe', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)

    fireEvent.click(await screen.findByTestId('settings-engine-test'))

    await waitFor(() => expect(healthCheck).toHaveBeenCalled())
    const badge = await screen.findByTestId('settings-engine-state')
    expect(badge).toHaveAttribute('data-engine-state', 'ok')
    expect(badge.textContent).toBe('settings.engineState.ok')
  })

  it('busy wird NICHT als offline/unreachable angezeigt', async () => {
    healthCheck.mockResolvedValueOnce({
      status: 'ok',
      ollama: false,
      models: [],
      active_tier: 'power',
      active_model: 'my-served-model',
      dgx_online: false,
      active_provider: 'openai_compatible',
      offline_capable: false,
      requires_internet: true,
      engine_online: false,
      engine_state: 'busy',
    })
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)

    const badge = await screen.findByTestId('settings-engine-state')
    expect(badge).toHaveAttribute('data-engine-state', 'busy')
    expect(badge).not.toHaveAttribute('data-engine-state', 'unreachable')
  })

  it('unreachable wird als nicht erreichbar gemeldet', async () => {
    healthCheck.mockResolvedValueOnce({
      status: 'ok',
      ollama: false,
      models: [],
      active_tier: 'offline',
      active_model: 'my-served-model',
      dgx_online: false,
      active_provider: 'openai_compatible',
      offline_capable: false,
      requires_internet: true,
      engine_online: false,
      engine_state: 'unreachable',
    })
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)

    const badge = await screen.findByTestId('settings-engine-state')
    expect(badge).toHaveAttribute('data-engine-state', 'unreachable')
  })

  // The refused case is the one the backend can state and the surface used to lose:
  // an engine that answers 401 read as "not reachable", which sends the user to the
  // network for a problem the key field on this same tab answers.
  it('an engine that refuses the credential is not reported as unreachable', async () => {
    healthCheck.mockResolvedValueOnce({
      status: 'ok',
      ollama: false,
      models: [],
      active_tier: 'offline',
      active_model: 'my-served-model',
      dgx_online: false,
      active_provider: 'openai_compatible',
      offline_capable: false,
      requires_internet: true,
      engine_online: false,
      engine_state: 'unreachable',
      engine_key_challenge: true,
      engine_key_configured: false,
    })
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)

    const badge = await screen.findByTestId('settings-engine-state')
    expect(badge).toHaveAttribute('data-engine-key', 'refused')
    expect(badge.textContent).toBe('settings.engineKeyChallenge')
    expect(badge.textContent).not.toBe('settings.engineState.unreachable')
    const keyRow = screen.getByTestId('engine-row-apikey')
    expect(keyRow.textContent).toContain('settings.engineKeyMissing')
    expect(keyRow.textContent).not.toContain('settings.apiKeyHint')
  })

  it('a refused key the run does hold reads differently from a missing one', async () => {
    healthCheck.mockResolvedValueOnce({
      status: 'ok',
      ollama: false,
      models: [],
      active_tier: 'offline',
      active_model: 'my-served-model',
      dgx_online: false,
      active_provider: 'openai_compatible',
      offline_capable: false,
      requires_internet: true,
      engine_online: false,
      engine_state: 'unreachable',
      engine_key_challenge: true,
      engine_key_configured: true,
    })
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)

    await screen.findByTestId('settings-engine-state')
    expect(screen.getByTestId('engine-row-apikey').textContent).toContain(
      'settings.engineKeyRejected',
    )
  })
})
