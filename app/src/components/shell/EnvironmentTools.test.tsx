/**
 * Ephe — wave B, B2/B3: EnvironmentTools (pin tests)
 *
 * GIVEN the opt-in scan of the AI tools already present (B2/B3)
 * WHEN rendered / scanned
 * THEN holds: no auto-scan (click only), rows with an auth dot + model chips, an
 *     honest pick derivation (no endpoint, no button) and URL scrubbing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const scanEnvironment = vi.fn()
vi.mock('@/lib/api/environment', () => ({
  scanEnvironment: (...a: unknown[]) => scanEnvironment(...a),
}))

import EnvironmentTools, { derivePick, scrubUrl } from './EnvironmentTools'
import type { MirrorTool } from '@/lib/api/environment'

const TOOLS: MirrorTool[] = [
  {
    tool: 'opencode',
    installed: true,
    config_path: '/home/u/.config/opencode/opencode.jsonc',
    providers: ['anthropic', 'http://127.0.0.1:11434/v1?key=sk-abc'],
    models: ['anthropic/claude-x', 'http://192.168.1.50:8000/v1'],
    auth_present: true,
  },
  {
    tool: 'codex',
    installed: false,
    config_path: '',
    providers: [],
    models: [],
    auth_present: false,
  },
] satisfies MirrorTool[]

beforeEach(() => {
  scanEnvironment.mockReset()
})

function renderWithPick(onPick?: Parameters<typeof EnvironmentTools>[0]['onPick']) {
  return render(<EnvironmentTools onPick={onPick} />)
}

describe('Opt-in-Vertrag', () => {
  it('scannt NICHT beim Mount — Daten erst nach Klick', async () => {
    scanEnvironment.mockResolvedValue({
      tools: TOOLS,
      summary: { installed: 1, with_models: ['opencode'] },
    })
    renderWithPick()
    expect(screen.queryByTestId('environment-scan-status')).toBeNull()
    expect(scanEnvironment).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('environment-scan-button'))
    await waitFor(() => expect(screen.getByTestId('environment-scan-status')).toBeTruthy())
    expect(scanEnvironment).toHaveBeenCalledTimes(1)
  })

  it('Fehler fail-soft sichtbar', async () => {
    scanEnvironment.mockRejectedValue(new Error('API 500'))
    renderWithPick()
    fireEvent.click(screen.getByTestId('environment-scan-button'))
    await waitFor(() => expect(screen.getByTestId('environment-error').textContent).toBe('API 500'))
  })
})

describe('Scan-Darstellung', () => {
  it('Rows mit Auth-Punkt, Modell-Chips, Nicht-Installierte zusammengefasst', async () => {
    scanEnvironment.mockResolvedValue({ tools: TOOLS, summary: { installed: 1, with_models: [] } })
    renderWithPick()
    fireEvent.click(screen.getByTestId('environment-scan-button'))
    await waitFor(() => screen.getByTestId('environment-row-opencode'))
    expect(screen.getByTestId('environment-auth-opencode').textContent).toBe('environment.authYes')
    // URL strings do not count as a model
    expect(screen.getByTestId('environment-model-opencode-anthropic/claude-x')).toBeTruthy()
    expect(screen.queryByTestId(/^environment-model-opencode-http/)).toBeNull()
    expect(screen.queryByTestId('environment-row-codex')).toBeNull()
    expect(screen.getByTestId('environment-scan-status').textContent).toContain(
      'environment.alsoFound',
    )
  })
})

describe('derivePick (ehrliche Vorauswahl)', () => {
  it('Ollama-Port → custom_ollama mit Endpunkt', () => {
    const pick = derivePick(TOOLS[0]!, 'llama3:8b')
    expect(pick).toEqual({
      providerKind: 'custom_ollama',
      endpoint: 'http://127.0.0.1:11434/v1',
      model: 'llama3:8b',
    })
  })

  it('OpenAI-kompatibler Endpunkt → openai_compatible', () => {
    const tool: MirrorTool = {
      ...TOOLS[0]!,
      providers: [],
      models: ['http://192.168.1.50:8000/v1', 'qwen'],
    }
    const pick = derivePick(tool, 'qwen')
    expect(pick?.providerKind).toBe('openai_compatible')
    expect(pick?.endpoint).toBe('http://192.168.1.50:8000/v1')
  })

  it('ohne Endpunkt → null (Chip bleibt informativ, kein stiller Fallback)', () => {
    const tool: MirrorTool = { ...TOOLS[0]!, providers: ['anthropic'], models: ['claude-x'] }
    expect(derivePick(tool, 'claude-x')).toBeNull()
  })

  it('scrubUrl entfernt Query-Parameter (nie Keys zeigen)', () => {
    expect(scrubUrl('http://127.0.0.1:11434/v1?key=sk-abc')).toBe('http://127.0.0.1:11434/v1')
  })
})

describe('Pick-Interaktion', () => {
  it('ableitbarer Chip ist ein Button und ruft onPick', async () => {
    scanEnvironment.mockResolvedValue({
      tools: TOOLS,
      summary: { installed: 1, with_models: ['opencode'] },
    })
    const onPick = vi.fn()
    renderWithPick(onPick)
    fireEvent.click(screen.getByTestId('environment-scan-button'))
    await waitFor(() => screen.getByTestId('environment-row-opencode'))
    const chip = screen.getByTestId('environment-model-opencode-anthropic/claude-x')
    expect(chip.tagName).toBe('BUTTON')
    fireEvent.click(chip)
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ providerKind: 'custom_ollama', model: 'anthropic/claude-x' }),
      TOOLS[0]!,
    )
  })

  it('nicht ableitbarer Chip ist ein span (informativ)', async () => {
    const tool: MirrorTool = { ...TOOLS[0]!, providers: ['anthropic'], models: ['claude-x'] }
    scanEnvironment.mockResolvedValue({ tools: [tool], summary: { installed: 1, with_models: [] } })
    renderWithPick(vi.fn())
    fireEvent.click(screen.getByTestId('environment-scan-button'))
    await waitFor(() => screen.getByTestId('environment-row-opencode'))
    expect(screen.getByTestId('environment-model-opencode-claude-x').tagName).toBe('SPAN')
  })
})
