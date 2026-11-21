/**
 * M3 (reference parity) — 2026-11-10: the row is the access side of the
 * composer: [+] [🛡 profile] [🎙] [model ▾] [◌ details ▾] [↑].
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChatInput from '@/components/dashboard/ChatInput'
import { getSetupStatus } from '@/lib/api'
import { forgetSetupGate } from '@/lib/setupGate'

vi.mock('@/lib/api', () => ({
  getModelProviders: vi.fn(() =>
    Promise.resolve({
      active: { provider: 'local_ollama', model: 'qwen3.8-flash-next', api_url: null },
      local_models: [],
      local_model_options: [],
    }),
  ),
  getSetupStatus: vi.fn(() =>
    Promise.resolve({
      configured: true,
      provider: 'local_ollama',
      model: null,
      url: null,
      reachable: true,
      available_models: [],
    }),
  ),
  getSettings: vi.fn(() =>
    Promise.resolve({ workspace_dir: '/tmp/ws', approval_profile: 'autonomous' }),
  ),
  listFs: vi.fn(() => Promise.resolve({ path: '/tmp/ws', entries: [] })),
  listSkills: vi.fn(() => Promise.resolve({ skills: [] })),
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    // The composer reads the interface language off the hook (context ring), so a
    // mock without `i18n` is a partial hook, not a smaller surface.
    i18n: { language: 'en' },
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
  }),
}))

beforeEach(() => {
  localStorage.clear()
  // R25: each test is its own app load. The gate answers once per load and shares that answer
  // with the composer, so a test that wants the *next* answer has to start a load.
  forgetSetupGate()
})

describe('composer chips (M3, reference pattern)', () => {
  it('access control, model chip and thinking chip in the action row', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    const access = await screen.findByTestId('composer-access-control')
    // The stored value in this fixture is the pre-register `autonomous`; the control
    // still names it from the same leaves the badge used.
    expect(access.textContent).toContain('chat.perm.autonomous')
    expect(access.getAttribute('data-profile')).toBe('autonomous')
    expect(screen.getByTestId('model-chip')).toBeTruthy()
    expect(screen.getByTestId('composer-thinking-chip')).toBeTruthy()
    // Thinking chip: the store holds no thinking messages → the 'off' branch
    expect(screen.getByTestId('composer-thinking-chip').textContent).toContain('chat.thinkingOff')
  })

  it('the thinking chip shows On when the session carries a thinking block', async () => {
    const { useChatStore } = await import('@/store/chatStore')
    useChatStore.setState({
      sessions: [
        {
          id: 's1',
          title: 'T',
          createdAt: 0,
          messages: [
            {
              id: 'a1',
              role: 'assistant',
              content: 'x',
              timestamp: 0,
              thinking: { start: 1, end: 2, text: 'y' },
            },
          ],
        },
      ],
      activeSessionId: 's1',
    })
    render(<ChatInput onSend={vi.fn()} />)
    const chip = await screen.findByTestId('composer-thinking-chip')
    expect(chip.textContent).toContain('chat.thinkingOn')
  })

  it('the send/stop button carries its testid (pinned to reference row 1)', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    expect(await screen.findByTestId('send-btn')).toBeTruthy()
    const { container } = render(<ChatInput onSend={vi.fn()} streaming onStop={vi.fn()} />)
    const stop = container.querySelector('[data-testid="stop-btn"]')
    expect(stop).toBeTruthy()
  })

  it('W19: with no engine the chip offers the setup re-entry over a silent default', async () => {
    vi.mocked(getSetupStatus).mockResolvedValueOnce({
      configured: false,
      skipped: true,
      provider: 'local_ollama',
      model: null,
      url: null,
      reachable: false,
      available_models: [],
    })
    render(<ChatInput onSend={vi.fn()} />)
    const chip = await screen.findByTestId('model-chip')
    await waitFor(() => expect(chip).toHaveAttribute('data-needs-setup', 'true'))
    expect(chip.textContent).toContain('chat.setupEngineChip')
    fireEvent.click(chip)
    const menu = screen.getByTestId('model-chip-menu')
    expect(menu.querySelector('[data-testid="model-chip-option-setup"]')).toBeTruthy()
  })
})
