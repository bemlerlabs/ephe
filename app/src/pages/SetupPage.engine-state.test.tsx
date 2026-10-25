// W18/A5 — first-run engine choice: the connection test shows the three-valued
// state from the probe (ok | busy | unreachable). "busy" is NOT "offline": the
// engine does answer, just not in time.
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

const probeProvider = vi.fn<
  () => Promise<{
    reachable: boolean
    models: string[]
    detail: string
    url?: string
    state: 'ok' | 'busy' | 'unreachable'
  }>
>(async () => ({
  reachable: true,
  models: ['my-served-model'],
  detail: 'http://10.1.2.3:8000 reachable · 1 model(s)',
  url: 'http://10.1.2.3:8000/v1',
  state: 'ok',
}))
const updateSettings = vi.fn(async () => ({}))
const resetSetup = vi.fn(async () => ({ configured: false }))
const skipSetup = vi.fn(async () => ({ configured: false, skipped: true }))
// W19: mount probe of the setup status — deliberately not-configured, so the
// auto-probe branch in the mount effect is not an extra probe call.
const getSetupStatus = vi.fn(async () => ({
  configured: false,
  skipped: false,
  provider: '',
  model: null,
  url: null,
  reachable: false,
  available_models: [],
}))
// R9: the auto-scan is part of the surface (mount + re-scan + preset click).
// Deliberately empty — these tests are about the state reported by a probe of
// their own, not about suggestions.
const detectEngines = vi.fn(async () => ({
  candidates: [],
  detected: [],
  first_reachable: -1,
}))

vi.mock('@/lib/api', () => ({
  probeProvider: (...a: unknown[]) => probeProvider(...(a as [])),
  updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
  resetSetup: () => resetSetup(),
  skipSetup: () => skipSetup(),
  getSetupStatus: () => getSetupStatus(),
  detectEngines: () => detectEngines(),
}))

import SetupPage from './SetupPage'

beforeEach(() => {
  probeProvider.mockClear()
  updateSettings.mockClear()
  skipSetup.mockClear()
})

describe('SetupPage Engine-Zustand (W18/A5)', () => {
  it('zeigt nach der Probe den Zustand ok', async () => {
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))

    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'ok'))
    expect(screen.getByTestId('setup-engine-state').textContent).toBe('setup.engineState.ok')
  })

  it('unterscheidet busy von unreachable', async () => {
    probeProvider.mockResolvedValueOnce({
      reachable: false,
      models: [],
      detail: 'http://10.1.2.3:8000 did not answer in time (busy)',
      state: 'busy',
    })
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))

    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'busy'))
    expect(status).not.toHaveAttribute('data-engine-state', 'unreachable')
    expect(screen.getByTestId('setup-engine-state').textContent).toBe('setup.engineState.busy')
  })

  it('fällt ohne state-Feld (Alt-Server) auf reachable/unreachable zurück', async () => {
    probeProvider.mockResolvedValueOnce({
      reachable: false,
      models: [],
      detail: 'http://10.1.2.3:8000 not reachable',
    } as never)
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))

    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'unreachable'))
  })

  it('Platzhalter der Endpunkt-Eingabe enthält keinen privaten Hostnamen', () => {
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    const input = screen.getByTestId('setup-endpoint') as HTMLInputElement
    expect(input.placeholder).not.toContain('ts.net')
    expect(input.placeholder).toContain('/v1')
  })
  // SCREEN_SPEC §2 (S3): the status plate arrives after the probe, when the eye has
  // already moved on to the form — `role="status"` is what carries it to a reader,
  // and `role="alert"` is what makes a refused engine the blocker it reads as.
  it('announces the two setup plates by their roles', async () => {
    probeProvider.mockRejectedValueOnce(new Error('the engine answered nothing'))
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))
    const error = await screen.findByTestId('setup-error')
    expect(error).toHaveAttribute('role', 'alert')

    probeProvider.mockResolvedValueOnce({
      reachable: true,
      models: ['m1'],
      url: 'http://10.1.2.3:8000/v1',
      detail: 'http://10.1.2.3:8000 reachable · 1 model(s)',
      state: 'ok',
    })
    fireEvent.click(screen.getByTestId('setup-probe'))
    const status = await screen.findByTestId('setup-status')
    // The live region is the always-mounted plate; a role only on the child that
    // arrives with its text is not reliably announced.
    expect(status.closest('[role="status"]')).not.toBeNull()
  })
})

describe('SetupPage Skip + API-Key (W19)', () => {
  it('Skip-Button ruft skipSetup und onDone — kein stiller Default', async () => {
    const onDone = vi.fn()
    render(<SetupPage onDone={onDone} />)
    fireEvent.click(screen.getByTestId('setup-skip'))
    await waitFor(() => expect(skipSetup).toBeCalled())
    await waitFor(() => expect(onDone).toBeCalled())
    expect(updateSettings).not.toBeCalled()
  })

  it('API-Key-Feld nur bei OpenAI-kompatibel und im Persist-Payload', async () => {
    render(<SetupPage onDone={vi.fn()} />)
    // Local chosen: no key field (Ollama needs none).
    fireEvent.click(screen.getByTestId('setup-option-local'))
    expect(screen.queryByTestId('setup-api-key')).toBeNull()
    // OpenAI-compatible: the field appears and the input lands in the persist payload.
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    const keyField = screen.getByTestId('setup-api-key') as HTMLInputElement
    expect(keyField).toBeTruthy()
    expect(keyField.type).toBe('password')
    fireEvent.change(keyField, { target: { value: 'test-key-123' } })
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))
    await screen.findByTestId('setup-status')
    await waitFor(() =>
      expect(screen.getByTestId('setup-status')).toHaveAttribute('data-engine-state', 'ok'),
    )
    fireEvent.click(screen.getByTestId('setup-finish'))
    await waitFor(() => expect(updateSettings).toBeCalled())
    const payload = (
      updateSettings.mock.calls[0] as unknown as [{ provider?: { api_key?: string } }]
    )[0]
    expect(payload.provider?.api_key).toBe('test-key-123')
  })

  // R36 (judge round 1, page 5): the probe row embedded the server's prose
  // ("… erreichbar · 1 Modelle") — mixed language plus a doubled URL. // language-gate: ignore (the German server detail this bar was written against; model_provider.py:60/:121 went English in the 2026-10-09 literal wave)
  // Expected: a structured row built from url + the i18n plural, with no
  // server prose inside the detail string — in either language.
  it('R36: Probe-Zeile strukturiert ohne Server-Prosa (kein Sprachmix)', async () => {
    probeProvider.mockResolvedValueOnce({
      reachable: true,
      models: ['m1'],
      url: 'http://10.1.2.3:8000/v1',
      detail: 'http://10.1.2.3 reachable · 1 model(s)',
      state: 'ok',
    })
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-option-openai'))
    fireEvent.change(screen.getByTestId('setup-endpoint'), {
      target: { value: 'http://10.1.2.3:8000/v1' },
    })
    fireEvent.click(screen.getByTestId('setup-probe'))
    const status = await screen.findByTestId('setup-status')
    await waitFor(() => expect(status).toHaveAttribute('data-engine-state', 'ok'))
    const line = status.textContent ?? ''
    expect(line).not.toContain('reachable')
    expect(line).not.toContain('model(s)')
    expect(line).toContain('setup.modelsFound')
  })

  // R45: quick provider picker — clicking 'OpenCode Zen' sets the endpoint and
  // probes with that endpoint immediately (no manual typing).
  it('R45: Quick-Pick OpenCode Zen setzt Endpunkt + sofortige Probe', async () => {
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-quick-opencode'))
    const input = screen.getByTestId('setup-endpoint') as HTMLInputElement
    expect(input.value).toBe('https://opencode.ai/zen/v1')
    await waitFor(() => {
      const calls = probeProvider.mock.calls as unknown as [string, string | undefined][]
      expect(
        calls.some((c) => c[0] === 'openai_compatible' && c[1] === 'https://opencode.ai/zen/v1'),
      ).toBe(true)
    })
  })

  // R45: Ollama quick pick — local_ollama without a URL, probed anyway.
  it('R45: Quick-Pick Ollama ist local_ollama ohne Endpunkt-Pflicht', async () => {
    render(<SetupPage onDone={vi.fn()} />)
    fireEvent.click(screen.getByTestId('setup-quick-ollama'))
    await waitFor(() => {
      const calls = probeProvider.mock.calls as unknown as [string, string | undefined][]
      // Ollama quick pick: provider=local_ollama with NO url.
      expect(calls.some((c) => c[0] === 'local_ollama' && !c[1])).toBe(true)
    })
  })

  // SCREEN_SPEC §2 / S3: the two plates a reader needs announced. The status plate
})
