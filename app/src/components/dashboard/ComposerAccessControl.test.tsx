/**
 * 2026-11-10 — the access rights stay in the composer, as one control.
 *
 * The mode moved to the header; the approval profile stayed where a tool call is
 * approved. The control shows the active right, opens the four values the server
 * accepts (`core/security_config.py::VALID_APPROVAL_PROFILES`), writes the pick
 * through `/api/settings/security`, and warns when the profile is Full Access.
 *
 * The engine rule is the part that must not drift: the profile is the ceiling
 * above the mode, so a profile pick may never rewrite a session's mode. The two
 * last tests hold that, and a refused write leaves the shown value alone.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'm', api_url: null },
    local_models: [],
    local_model_options: [],
  })),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })),
  saveSecuritySettings: vi.fn(async (payload: { approval_profile: string }) => ({
    approval_profile: payload.approval_profile,
    sandbox_enabled: false,
  })),
  setModelProvider: vi.fn(async () => ({})),
  getSetupStatus: vi.fn(async () => ({ configured: true, provider: 'local_ollama' })),
  listFs: vi.fn(async () => ({ path: '/tmp/ws', parent: null, entries: [] })),
  listSkills: vi.fn(async () => ({ skills: [] })),
  transcribeAudio: vi.fn(async () => ''),
}))

vi.mock('@/lib/api', () => api)

vi.mock('react-i18next', async () => {
  const bundle = (await import('@/locales/en.json')).default as Record<string, unknown>
  const read = (key: string): string | undefined => {
    let node: unknown = bundle
    for (const part of key.split('.')) {
      if (typeof node !== 'object' || node === null) return undefined
      node = (node as Record<string, unknown>)[part]
    }
    return typeof node === 'string' ? node : undefined
  }
  return {
    initReactI18next: { type: '3rdParty', init: () => undefined },
    useTranslation: () => ({
      i18n: { language: 'en' },
      t: (key: string, opts?: { defaultValue?: string }) =>
        read(key) ?? (opts?.defaultValue as string | undefined) ?? key,
    }),
  }
})

import ChatInput from './ChatInput'
import { useChatStore } from '@/store/chatStore'

const trigger = () => screen.getByTestId('composer-access-control')
const sessionMode = (): string | undefined =>
  useChatStore.getState().sessions.find((x) => x.id === useChatStore.getState().activeSessionId)
    ?.mode

beforeEach(() => {
  vi.clearAllMocks()
  api.getSettings.mockResolvedValue({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
  useChatStore.getState().createSession('Access')
  useChatStore.getState().setSessionMode(useChatStore.getState().activeSessionId!, 'operator')
})

describe('the composer access control', () => {
  it('shows the active right and names it for a screen reader', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(trigger().textContent).toContain('Manual'))
    expect(trigger().getAttribute('aria-label')).toBe('Approvals: Manual')
    expect(trigger().getAttribute('aria-haspopup')).toBe('menu')
    expect(trigger().getAttribute('data-profile')).toBe('strict')
  })

  it('offers the four profiles and writes the pick', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(trigger().textContent).toContain('Manual'))
    fireEvent.click(trigger())

    expect(screen.getByTestId('composer-access-menu')).toBeTruthy()
    for (const key of ['strict', 'session', 'plan', 'full']) {
      const row = screen.getByTestId(`composer-access-${key}`)
      expect(row.getAttribute('role')).toBe('menuitemradio')
      expect(row.getAttribute('aria-checked')).toBe(key === 'strict' ? 'true' : 'false')
    }

    fireEvent.click(screen.getByTestId('composer-access-session'))
    await waitFor(() =>
      expect(api.saveSecuritySettings).toHaveBeenCalledWith({ approval_profile: 'session' }),
    )
    await waitFor(() => expect(trigger().textContent).toContain('Session'))
    expect(trigger().getAttribute('aria-label')).toBe('Approvals: Session')
  })

  it('warns at Full Access, on the control and in the menu', async () => {
    api.getSettings.mockResolvedValue({ workspace_dir: '/tmp/ws', approval_profile: 'full' })
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(trigger().getAttribute('data-profile')).toBe('full'))
    expect(trigger().getAttribute('data-warning')).toBe('full')
    expect(trigger().className).toContain('text-status-warning')
    fireEvent.click(trigger())
    const warning = screen.getByTestId('composer-access-full-warning')
    expect(warning.textContent).toContain('without asking')
    expect(trigger().getAttribute('aria-checked')).toBeNull()
  })

  it('never changes the session mode — the profile is the ceiling above it', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(trigger().textContent).toContain('Manual'))
    fireEvent.click(trigger())
    fireEvent.click(screen.getByTestId('composer-access-full'))
    await waitFor(() => expect(trigger().textContent).toContain('Full access'))
    expect(sessionMode()).toBe('operator')
  })

  it('closes on Escape, through the composer’s one escape chain', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(trigger().textContent).toContain('Manual'))
    fireEvent.click(trigger())
    expect(screen.getByTestId('composer-access-menu')).toBeTruthy()
    // Focus sits in the text field after a click on the control row; the composer's
    // chain closes the topmost popup, so Escape must not need the menu focused.
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('composer-access-menu')).toBeNull())
  })

  it('keeps the shown value when the write is refused', async () => {
    api.saveSecuritySettings.mockRejectedValueOnce(new Error('refused'))
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(trigger().textContent).toContain('Manual'))
    fireEvent.click(trigger())
    fireEvent.click(screen.getByTestId('composer-access-full'))

    const failed = await screen.findByTestId('composer-access-failed')
    expect(failed.getAttribute('role')).toBe('status')
    expect(trigger().textContent).toContain('Manual')
    expect(trigger().getAttribute('data-profile')).toBe('strict')
  })
})
