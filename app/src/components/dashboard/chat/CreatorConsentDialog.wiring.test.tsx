/**
 * The composer asks for Creator Mode; it does not hand it out.
 *
 * The tile is the entry point, and the guard behind it refuses every call the
 * session has not been granted (`80e3852f`). So the two halves have to meet in
 * one honest sequence on the surface: picking Creator opens the consent sheet
 * and leaves the session on the mode it was already using, the sheet's answer
 * is written for that session, and only then does the session switch. A tile
 * that set the mode first would leave the user reading refusals for a mode they
 * had already entered.
 *
 * The other three tiles are part of this contract: they switch as they did,
 * because consent is a Creator thing and nothing else may inherit the dialog.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
  }),
}))

const api = vi.hoisted(() => ({
  CREATOR_PRIVILEGES: ['code', 'files', 'network'],
  getCreatorConsent: vi.fn(),
  putCreatorConsent: vi.fn(),
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'x', api_url: null },
    local_models: [],
    local_model_options: [],
  })),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })),
  getSetupStatus: vi.fn(async () => ({ configured: true, provider: 'local_ollama' })),
  listFs: vi.fn(async () => ({ path: '/tmp/ws', parent: null, entries: [] })),
  listSkills: vi.fn(async () => ({ skills: [] })),
  transcribeAudio: vi.fn(async () => ''),
  setModelProvider: vi.fn(async () => ({})),
}))

vi.mock('@/lib/api', () => api)

import ChatInput from '../ChatInput'
import { useChatStore } from '@/store/chatStore'

const storedMode = (): string =>
  String((useChatStore.getState().sessions[0] as { mode?: string }).mode)

const openModeMenu = () => {
  fireEvent.click(screen.getByTestId('composer-mode-selector'))
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.getCreatorConsent.mockResolvedValue({
    session_id: 'sess-1',
    privileges: ['code', 'files', 'network'],
    held: [],
    mode: 'creator',
  })
  api.putCreatorConsent.mockResolvedValue({
    session_id: 'sess-1',
    privileges: ['code', 'files', 'network'],
    held: ['code'],
    mode: 'creator',
  })
  useChatStore.setState({
    sessions: [
      {
        id: 'sess-1',
        title: 'Creator wiring',
        messages: [],
        mode: 'operator',
        createdAt: 1,
        updatedAt: 1,
      },
    ],
    activeSessionId: 'sess-1',
    currentSession: null,
    hydrated: true,
  } as never)
})

describe('entering Creator Mode from the composer', () => {
  it('opens the sheet and leaves the session on the mode it had', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('chat-input')).toBeTruthy())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-creator'))

    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())
    expect(storedMode()).toBe('operator')
    expect(api.putCreatorConsent).not.toHaveBeenCalled()
  })

  it('writes the answer for this session, then switches it', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('chat-input')).toBeTruthy())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-creator'))
    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())

    fireEvent.click(screen.getByTestId('creator-consent-code-input'))
    fireEvent.click(screen.getByTestId('creator-consent-enter'))

    await waitFor(() => expect(api.putCreatorConsent).toHaveBeenCalledWith('sess-1', ['code']))
    await waitFor(() => expect(storedMode()).toBe('creator'))
  })

  it('keeps the session where it was when the user closes the sheet', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('chat-input')).toBeTruthy())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-creator'))
    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())

    fireEvent.click(screen.getByTestId('creator-consent-cancel'))

    await waitFor(() => expect(screen.queryByTestId('creator-consent-code')).toBeNull())
    expect(api.putCreatorConsent).not.toHaveBeenCalled()
    expect(storedMode()).toBe('operator')
  })

  it("asks again the next time, because the grant is the session's, not the app's", async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('chat-input')).toBeTruthy())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-creator'))
    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())
    fireEvent.click(screen.getByTestId('creator-consent-cancel'))
    await waitFor(() => expect(screen.queryByTestId('creator-consent-code')).toBeNull())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-creator'))
    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())
    expect(api.getCreatorConsent).toHaveBeenCalledTimes(2)
  })

  it('leaves the session on its old mode when the consent write fails', async () => {
    api.putCreatorConsent.mockRejectedValue(new Error('backend down'))
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('chat-input')).toBeTruthy())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-creator'))
    await waitFor(() => expect(screen.getByTestId('creator-consent-code')).toBeTruthy())

    fireEvent.click(screen.getByTestId('creator-consent-code-input'))
    fireEvent.click(screen.getByTestId('creator-consent-enter'))

    await waitFor(() => expect(screen.getByTestId('creator-consent-write-failed')).toBeTruthy())
    expect(storedMode()).toBe('operator')
  })

  it('switches the other three tiles without a sheet', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('chat-input')).toBeTruthy())

    openModeMenu()
    fireEvent.click(screen.getByTestId('composer-mode-architect'))

    await waitFor(() => expect(storedMode()).toBe('architect'))
    expect(screen.queryByTestId('creator-consent-code')).toBeNull()
    expect(api.getCreatorConsent).not.toHaveBeenCalled()
  })
})
