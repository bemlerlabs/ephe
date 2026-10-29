// P2 — the first-run button that sets the engine up for this machine.
//
// The rule it must keep: the click is the consent, the scan is the evidence, and
// nothing is written when the scan reaches no engine. The memory the endpoint
// reports decides which of the offered models fits.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

const updateSettings = vi.fn(async () => ({}))
let detectPayload: Record<string, unknown> = { candidates: [], detected: [], first_reachable: -1 }
const detectEngines = vi.fn(async () => detectPayload as never)
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

vi.mock('@/lib/api', () => ({
  probeProvider: vi.fn(async () => ({ reachable: false, models: [], detail: '', state: 'unreachable' })),
  updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
  resetSetup: vi.fn(async () => ({ configured: false })),
  skipSetup: vi.fn(async () => ({ configured: false, skipped: true })),
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
}))

import SetupPage from './SetupPage'

function localOllama(): Record<string, unknown> {
  return {
    candidates: [{ provider: 'local_ollama', url: 'http://127.0.0.1:11434' }],
    detected: [
      {
        provider: 'local_ollama',
        url: 'http://127.0.0.1:11434',
        reachable: true,
        models: ['qwen2.5-coder:32b', 'llama3:8b'],
        detail: '',
        state: 'ok',
      },
    ],
    first_reachable: 0,
  }
}

const realFetch = globalThis.fetch

beforeEach(() => {
  updateSettings.mockClear()
  detectEngines.mockClear()
  detectPayload = { candidates: [], detected: [], first_reachable: -1 }
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/system/metrics')) {
      return new Response(JSON.stringify({ mem_total_gb: 24 }), { status: 200 })
    }
    return new Response('{}', { status: 200 })
  }) as typeof fetch
})

afterEach(() => {
  globalThis.fetch = realFetch
})

describe('one-click setup (P2)', () => {
  it('writes the fitting model of the engine that answered, on the click', async () => {
    detectPayload = localOllama()
    const onDone = vi.fn()
    render(<SetupPage onDone={onDone} />)

    fireEvent.click(await screen.findByTestId('setup-one-click'))

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({
        provider: { type: 'local_ollama', model: 'llama3:8b', endpoint: undefined },
      }),
    )
    expect(onDone).toHaveBeenCalled()
  })

  it('writes nothing when no engine answered, and says so', async () => {
    render(<SetupPage onDone={vi.fn()} />)

    fireEvent.click(await screen.findByTestId('setup-one-click'))

    await waitFor(() =>
      expect(screen.getByTestId('setup-one-click-hint').textContent).toBe('setup.oneClickNone'),
    )
    expect(updateSettings).not.toHaveBeenCalled()
  })
})
