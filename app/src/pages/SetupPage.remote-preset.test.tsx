// R9 (field finding) — clicking a remote preset leads to a VERIFIED state.
// Until then: setKind + setProbeState(null) and nothing else, so the click deleted
// the auto-detection and left the surface empty ("nothing useful happens"). The
// suggestion comes from /api/setup/detect — engine.json, endpoint history, env and
// this machine's loopback finds. The surface never invents a host; when no
// candidate exists, it says so.
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

beforeEach(() => {
  probeProvider.mockClear()
  detectEngines.mockClear()
  detectPayload = { candidates: [], detected: [], first_reachable: -1 }
})

describe('SetupPage Remote-Preset-Klick (R9)', () => {
  it('übernimmt beim Klick auf „Ollama remote“ den eigenen Endpunkt und prüft ihn', async () => {
    detectPayload = {
      candidates: [
        { provider: 'openai_compatible', url: 'http://gpu-host.example:8000/v1' },
        { provider: 'custom_ollama', url: 'http://lan-box.example:11434' },
      ],
      detected: [
        {
          provider: 'openai_compatible',
          url: 'http://gpu-host.example:8000/v1',
          reachable: true,
          models: ['a-model'],
          detail: '',
          state: 'ok',
        },
        {
          provider: 'custom_ollama',
          url: 'http://lan-box.example:11434',
          reachable: true,
          models: ['gemma4:12b'],
          detail: '',
          state: 'ok',
        },
      ],
      first_reachable: 0,
    }
    render(<SetupPage onDone={vi.fn()} />)
    // Mount no longer picks an engine: it offers the found one (W3-26). Waiting for
    // the offer keeps the click below deterministic against the mount-time scan.
    await screen.findByTestId('setup-offer')

    fireEvent.click(screen.getByTestId('setup-option-custom'))

    const input = await screen.findByTestId('setup-endpoint')
    await waitFor(() => expect(input).toHaveValue('http://lan-box.example:11434'))
    await waitFor(() =>
      expect(
        probeProvider.mock.calls.some(
          (c) => c[0] === 'custom_ollama' && c[1] === 'http://lan-box.example:11434',
        ),
      ).toBe(true),
    )
    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'ok'))
  })

  it('nennt die Herkunft des Vorschlags: gespeicherte Engine, nicht erfundener Host', async () => {
    detectPayload = {
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
      first_reachable: -1,
    }
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    const chip = await screen.findByTestId('setup-suggestion')
    expect(chip.getAttribute('data-suggestion-source')).toBe('saved')
  })

  it('ein Loopback-Scan-Fund heißt „Scan“, nicht „deine Engine“', async () => {
    detectPayload = {
      candidates: [
        {
          provider: 'openai_compatible',
          url: 'http://127.0.0.1:8000/v1',
          hint: 'typisch für vLLM', // language-gate: ignore — mirrors the pair _ENGINE_PORTS really sends
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
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    const chip = await screen.findByTestId('setup-suggestion')
    expect(chip.getAttribute('data-suggestion-source')).toBe('scan')
  })

  it('ohne Kandidat dieser Klasse wird kein Host erfunden und die Fläche erklärt es', async () => {
    detectPayload = {
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
    render(<SetupPage onDone={vi.fn()} />)
    probeProvider.mockClear()

    fireEvent.click(screen.getByTestId('setup-option-custom'))

    const note = await screen.findByTestId('setup-suggestion-none')
    expect(note.textContent).toContain('setup.noEndpointRemote')
    const input = screen.getByTestId('setup-endpoint') as HTMLInputElement
    expect(input.value).toBe('')
    expect(probeProvider.mock.calls.some((c) => c[0] === 'custom_ollama')).toBe(false)
    expect(screen.getByTestId('setup-finish')).toBeDisabled()
  })

  it('unreachable Kandidat: echte Prüfung, ehrliche Meldung, nächster Schritt', async () => {
    detectPayload = {
      candidates: [{ provider: 'custom_ollama', url: 'http://lan-box.example:11434' }],
      detected: [
        {
          provider: 'custom_ollama',
          url: 'http://lan-box.example:11434',
          reachable: false,
          models: [],
          detail: '',
          state: 'unreachable',
        },
      ],
      first_reachable: -1,
    }
    probeProvider.mockResolvedValueOnce({
      reachable: false,
      models: [],
      detail: 'http://lan-box.example:11434 not reachable',
      state: 'unreachable',
    })
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-custom'))

    await waitFor(() =>
      expect(
        probeProvider.mock.calls.some(
          (c) => c[0] === 'custom_ollama' && c[1] === 'http://lan-box.example:11434',
        ),
      ).toBe(true),
    )
    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'unreachable'))
    expect(screen.getByTestId('setup-finish')).toBeDisabled()
  })
})
