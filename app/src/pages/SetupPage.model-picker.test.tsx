// S2 — the setup host keeps its own contract while the shared picker runs inside it:
// the same id and test-id, the borrowed-key note under it, the finish button gated on a
// choice, and no choice made for the user. One engine that answers with exactly one
// model may be filled in — that is not a silent default, it is the only answer there is.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) => (opts?.returnObjects ? [] : k),
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const probe = vi.fn()
const setupStatus = vi.fn(async () => ({
  configured: false,
  skipped: false,
  provider: '',
  model: null,
  url: null,
  reachable: false,
  available_models: [],
  candidates: [],
}))

vi.mock('@/lib/api', () => ({
  probeProvider: (...args: unknown[]) => probe(...(args as [])),
  updateSettings: vi.fn(async () => ({})),
  resetSetup: vi.fn(async () => ({ configured: false })),
  skipSetup: vi.fn(async () => ({ configured: false, skipped: true })),
  getSetupStatus: () => setupStatus(),
  detectEngines: async () => ({ candidates: [], detected: [], first_reachable: -1 }),
}))

import SetupPage from './SetupPage'

async function probeOpenai(
  models: string[],
  model = 'saved-model',
  extra: Record<string, unknown> = {},
) {
  setupStatus.mockResolvedValue({
    configured: true,
    skipped: false,
    provider: 'openai_compatible',
    model,
    url: 'http://10.1.2.3:8000/v1',
    reachable: true,
    available_models: models,
    candidates: [],
  } as never)
  probe.mockResolvedValue({
    reachable: true,
    models,
    detail: 'server-prosa', // language-gate: ignore — the server detail the route really returns
    url: 'http://10.1.2.3:8000/v1',
    state: 'ok',
    ...extra,
    model_details: models.map((id) => ({
      id,
      name: null,
      context_window: null,
      price_in_per_m: null,
      price_out_per_m: null,
      is_free: null,
      supports_tools: null,
      supports_vision: null,
    })),
  })
  render(<SetupPage onDone={vi.fn()} />)
  // The mount scan settles first: it is what remembers the model this device has
  // already chosen, and a probe fired before it would have nothing to restore.
  await waitFor(() => expect(setupStatus).toHaveBeenCalled())
  fireEvent.click(screen.getByTestId('setup-option-openai'))
  fireEvent.change(screen.getByTestId('setup-endpoint'), {
    target: { value: 'http://10.1.2.3:8000/v1' },
  })
  fireEvent.click(screen.getByTestId('setup-probe'))
}

beforeEach(() => {
  probe.mockReset()
  window.localStorage.clear()
})

describe('SetupPage model picker (S2)', () => {
  it('leaves the choice open when the engine answers with several models', async () => {
    await probeOpenai(['alpha', 'beta', 'gamma'], '')
    const trigger = await screen.findByTestId('setup-model')
    await waitFor(() => expect(trigger.textContent).toContain('modelPicker.choose'))
    expect(screen.getByTestId('setup-finish')).toBeDisabled()
  })

  it('fills in the only model an engine offers', async () => {
    await probeOpenai(['only-model'], '')
    const trigger = await screen.findByTestId('setup-model')
    await waitFor(() => expect(trigger.textContent).toContain('only-model'))
  })

  it('restores the saved model instead of the first row', async () => {
    await probeOpenai(['alpha', 'beta', 'gamma'], 'beta')
    const trigger = await screen.findByTestId('setup-model')
    await waitFor(() => expect(trigger.textContent).toContain('beta'))
  })

  it('searches the list and writes the row the user clicked', async () => {
    await probeOpenai(['alpha', 'beta', 'gamma'], '')
    const trigger = await screen.findByTestId('setup-model')
    await waitFor(() => expect(trigger.textContent).toContain('modelPicker.choose'))
    fireEvent.click(trigger)
    fireEvent.change(screen.getByTestId('setup-model-search'), { target: { value: 'gam' } })
    const gamma = screen.getByTestId('setup-model-row-gamma')
    fireEvent.click(within(gamma).getByTitle(/gamma/))
    await waitFor(() => expect(trigger.textContent).toContain('gamma'))
    expect(screen.getByTestId('setup-finish')).toBeEnabled()
  })

  it('brings the remembered model back from the status route alone', async () => {
    // The mount scan is the whole path here: no preset click, no probe. A user with
    // three models and one chosen must see the chosen one in the plate.
    setupStatus.mockResolvedValue({
      configured: true,
      skipped: false,
      provider: 'openai_compatible',
      model: 'beta',
      url: 'http://10.1.2.3:8000/v1',
      reachable: true,
      available_models: ['alpha', 'beta', 'gamma'],
      candidates: [],
    } as never)
    render(<SetupPage onDone={vi.fn()} />)
    const trigger = await screen.findByTestId('setup-model')
    await waitFor(() => expect(trigger.textContent).toContain('beta'))
    expect(screen.getByTestId('setup-finish')).toBeEnabled()
  })

  it('keeps the borrowed-key note under the picker', async () => {
    await probeOpenai(['alpha', 'beta'], '', { key_source: 'foreign' })
    const trigger = await screen.findByTestId('setup-model')
    expect(await screen.findByTestId('setup-borrowed-key')).toBeTruthy()
    // the note sits under the control it explains, not beside the engine list
    expect(trigger.compareDocumentPosition(screen.getByTestId('setup-borrowed-key'))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })
})
