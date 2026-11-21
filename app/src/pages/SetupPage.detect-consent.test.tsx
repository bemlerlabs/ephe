// W3-26 — one-click engine detection as explicit consent.
//
// The mount scan used to write the first reachable engine straight into the choice
// (provider + endpoint + model), so a user could click "Save" without ever deciding.
// AGENTS.md is the opposite rule: the engine belongs to the user, there is no silent
// default. Now a hit becomes an offer — "Ollama found, use it?" — and the choice is
// written only when the user clicks it. These tests pin both halves: nothing applied
// before the click, the offered class and endpoint applied and probed after it.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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

const probeProvider = vi.fn(
  async (
    _provider: string,
    url?: string,
  ): Promise<{
    reachable: boolean
    models: string[]
    detail: string
    url?: string
    state: 'ok' | 'busy' | 'unreachable'
  }> => ({
    reachable: true,
    models: ['picked-model'],
    detail: 'server-prosa',
    url,
    state: 'ok',
  }),
)
const getSetupStatus = vi.fn(async () => ({
  configured: false,
  skipped: false,
  provider: '',
  model: null,
  url: null,
  reachable: false,
  available_models: [],
  candidates: [],
}))
let detectPayload: Record<string, unknown> = {
  candidates: [],
  detected: [],
  first_reachable: -1,
}
const detectEngines = vi.fn(async () => detectPayload as never)

vi.mock('@/lib/api', () => ({
  probeProvider: (...a: unknown[]) => probeProvider(...(a as [string, string | undefined])),
  updateSettings: vi.fn(async () => ({})),
  resetSetup: vi.fn(async () => ({ configured: false })),
  skipSetup: vi.fn(async () => ({ configured: false, skipped: true })),
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
}))

import SetupPage from './SetupPage'

/** A scan that finds one reachable OpenAI-compatible engine with a model. */
function reachableOpenAi(): Record<string, unknown> {
  return {
    candidates: [{ provider: 'openai_compatible', url: 'http://gpu-host.example:8000/v1' }],
    detected: [
      {
        provider: 'openai_compatible',
        url: 'http://gpu-host.example:8000/v1',
        reachable: true,
        models: ['a-model'],
        detail: '',
        state: 'ok',
      },
    ],
    first_reachable: 0,
  }
}

beforeEach(() => {
  probeProvider.mockClear()
  detectEngines.mockClear()
  detectPayload = { candidates: [], detected: [], first_reachable: -1 }
})

describe('setup detection is an offer, not a silent default (W3-26)', () => {
  it('offers the detected engine and applies nothing until the offer is used', async () => {
    detectPayload = reachableOpenAi()
    render(<SetupPage onDone={vi.fn()} />)

    const offer = await screen.findByTestId('setup-offer')
    // The offer names its source and the short engine name in the sentence.
    expect(offer.getAttribute('data-offer-source')).toBe('saved')
    expect(screen.getByTestId('setup-offer-text').textContent).toBe('setup.detectOfferSaved')

    // Before the click: no engine selected, nothing probed, save still blocked.
    expect(screen.queryByTestId('setup-status')).toBeNull()
    expect(screen.getByTestId('setup-finish')).toBeDisabled()
    expect(probeProvider).not.toHaveBeenCalled()
  })

  it('applies and verifies the offered engine on the one click that consents', async () => {
    detectPayload = reachableOpenAi()
    render(<SetupPage onDone={vi.fn()} />)

    fireEvent.click(await screen.findByTestId('setup-offer-use'))

    // The offered class and endpoint are now the active choice, and truly probed.
    const input = await screen.findByTestId('setup-endpoint')
    await waitFor(() => expect(input).toHaveValue('http://gpu-host.example:8000/v1'))
    await waitFor(() =>
      expect(
        probeProvider.mock.calls.some(
          (c) => c[0] === 'openai_compatible' && c[1] === 'http://gpu-host.example:8000/v1',
        ),
      ).toBe(true),
    )
    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'ok'))
  })

  it('a dismissed offer leaves the engine unselected', async () => {
    detectPayload = reachableOpenAi()
    render(<SetupPage onDone={vi.fn()} />)

    fireEvent.click(await screen.findByTestId('setup-offer-dismiss'))

    await waitFor(() => expect(screen.queryByTestId('setup-offer')).toBeNull())
    expect(screen.queryByTestId('setup-status')).toBeNull()
    expect(screen.getByTestId('setup-finish')).toBeDisabled()
    expect(probeProvider).not.toHaveBeenCalled()
  })

  it('a scan hit from the loopback sweep is offered as a scan, not as the saved engine', async () => {
    detectPayload = {
      candidates: [
        {
          provider: 'openai_compatible',
          url: 'http://127.0.0.1:8000/v1',
          hint_code: 'vllm',
          sweep: true,
        },
      ],
      detected: [
        {
          provider: 'openai_compatible',
          url: 'http://127.0.0.1:8000/v1',
          reachable: true,
          models: ['a-model'],
          detail: '',
          state: 'ok',
        },
      ],
      first_reachable: 0,
    }
    render(<SetupPage onDone={vi.fn()} />)

    const offer = await screen.findByTestId('setup-offer')
    expect(offer.getAttribute('data-offer-source')).toBe('scan')
  })
})
