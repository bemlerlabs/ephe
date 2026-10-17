/**
 * Ephe — W14/P1-10: the engine badge tells the provider types apart.
 *
 * GIVEN  an active provider from /api/model/providers
 * WHEN   the composer renders
 * THEN   the badge shows Ollama-local or Ollama-remote —
 *        finding 2026-10-01: on openai_compatible (not offline-capable) the cap
 *        stays OFF: the always-visible „Remote engine" looked orphaned and it
 *        duplicated the status bar + the model chip.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChatInput from '@/components/dashboard/ChatInput'
import { getModelProviders } from '@/lib/api'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getModelProviders: vi.fn(async () => ({}) as never),
    getSetupStatus: vi.fn(async () => ({
      configured: true,
      provider: 'local_ollama',
      model: null,
      url: null,
      reachable: true,
      available_models: [],
    })),
    getSettings: async () => ({ workspace_dir: '/tmp/ws' }),
    listFs: async () => ({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      entries: [],
    }),
    listSkills: async () => ({ skills: [] }),
  }
})

const providers = (active: Record<string, unknown>, contextWindow: number | null = null) =>
  vi.mocked(getModelProviders).mockResolvedValueOnce({
    active,
    providers: [],
    local_models: [],
    local_model_options: [],
    context_window: contextWindow,
  } as never)

describe('ChatInput Engine-Badge (W14/P1-10)', () => {
  it('local_ollama → "… Ollama" mit Offline-Farbe', async () => {
    providers({ provider: 'local_ollama', model: 'gemma4:12b', offline_capable: true })
    render(<ChatInput onSend={vi.fn()} />)
    expect(await screen.findByText(/Ollama/)).toBeTruthy()
  })

  it('custom_ollama → Remote-Variante mit Ollama-Kennung', async () => {
    providers({ provider: 'custom_ollama', model: 'gemma4:12b', offline_capable: true })
    render(<ChatInput onSend={vi.fn()} />)
    expect(await screen.findByText(/Remote · Ollama/i)).toBeTruthy()
  })

  it('openai_compatible → keine Kappe („Remote engine" wirkt verwaist; Status lebt in Statusleiste + Chip)', async () => {
    providers(
      { provider: 'openai_compatible', model: 'qwen3.8-flash-next', offline_capable: false },
      262144,
    )
    render(<ChatInput onSend={vi.fn()} />)
    // Wait until the active provider has arrived in the model chip — only then is
    // the badge decision (offline_capable=false → no cap) made.
    expect(await screen.findByText(/qwen3\.8-flash-next/)).toBeTruthy()
    expect(screen.queryByText(/Remote engine/)).toBeNull()
  })
})
