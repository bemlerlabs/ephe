/**
 * W19 keep-its-word: the setup screen says the chat stays read-only until an
 * engine is chosen, and /api/chat/stream refuses (409 setup_required) until then.
 * The composer must agree: with no engine the Send control is off, its reason
 * sits on the control, and Enter sends nothing — no posted message, no turn
 * that can never run, no "stream could not be started" bubble.
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
      skipped: false,
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
    i18n: { language: 'en' },
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
  }),
}))

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  forgetSetupGate()
})

describe('composer with no engine chosen', () => {
  it('keeps Send off and names the reason on the control', async () => {
    vi.mocked(getSetupStatus).mockResolvedValueOnce({
      configured: false,
      skipped: true,
      provider: '',
      model: null,
      url: null,
      reachable: false,
      available_models: [],
    })
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hello' } })
    const send = await screen.findByTestId('send-btn')
    await waitFor(() => expect(send).toBeDisabled())
    expect(send.getAttribute('title')).toBe('chat.sendNeedsEngine')
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.click(send)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('sends again once an engine answers', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hello' } })
    const send = await screen.findByTestId('send-btn')
    await waitFor(() => expect(send).toBeEnabled())
    expect(send.getAttribute('title')).toBeNull()
    fireEvent.click(send)
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello', undefined))
  })
})
