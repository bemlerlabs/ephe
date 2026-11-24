// The settings sheet is mounted by its own open (`pages/SettingsPage.tsx:14`), so the
// window `focusin` recorder in `index.tsx:154-161` is not installed yet when the rail
// button is pressed: nothing is recorded, and the close has to answer without an invoker.
// Both directions of that close are pinned here, plus the two conditions the shared
// handback checks on the invoker (`!== document.body`, `!closest('[inert]')`
// — `hooks/useFocusReturn.ts:57-67`). The panel's own copy of this contract drifted on
// exactly those two and no case in the tree read them.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getSettings: vi.fn(async () => ({
      provider: { type: 'openai_compatible', model: 'm', endpoint: 'http://x/v1' },
      memory_enabled: true,
      language: 'de',
      theme: 'dark',
    })),
    updateSettings: vi.fn(async () => ({})),
    healthCheck: vi.fn(async () => ({
      status: 'ok',
      ollama: false,
      models: [],
      active_tier: 'power',
      active_model: 'm',
      dgx_online: true,
      active_provider: 'openai_compatible',
      offline_capable: false,
      requires_internet: true,
      engine_online: true,
      engine_state: 'ok',
    })),
    getModelProviders: vi.fn(async () => ({
      active: {},
      providers: [],
      local_models: [],
      local_model_options: [],
    })),
    getMemoryStats: vi.fn(async () => ({ total: 0 })),
    clearMemory: vi.fn(async () => ({ cleared: true })),
    getMobileQR: vi.fn(async () => ({
      url: '',
      qr_base64: '',
      mode: 'lan',
      is_public: false,
      requires_internet: false,
      lan_reachable: true,
      message: '',
    })),
    getMobileStatus: vi.fn(async () => ({ connected: false })),
    listSkills: vi.fn(async () => ({ skills: [], total: 0 })),
    getImageSettings: vi.fn(async () => ({
      base_url: '',
      model: '',
      has_api_key: false,
      api_key_hint: '',
    })),
    saveImageSettings: vi.fn(async () => ({
      base_url: '',
      model: '',
      has_api_key: false,
      api_key_hint: '',
    })),
    testImageEndpoint: vi.fn(async () => ({
      reachable: false,
      models: [],
      base_url_used: '',
      detail: '',
    })),
    getSchedulePresets: vi.fn(async () => ({ presets: [] })),
    getScheduleResults: vi.fn(async () => ({ results: [] })),
    listSchedules: vi.fn(async () => ({ jobs: [] })),
    getTasks: vi.fn(async () => []),
    fileUrl: (p: string) => p,
    getNetworkStatus: vi.fn(async () => ({
      bind_host: '127.0.0.1',
      bind_port: 8765,
      lan: false,
      setup_mode: false,
      token_required: false,
      file_roots: [],
      proxy_extra_ports: [],
      allow_private_fetches: false,
    })),
    getHooks: vi.fn(async () => ({
      enabled: true,
      path: '/Users/x/.ephe/hooks.json',
      exists: false,
      events: [],
      recent: [],
    })),
    exportMemoryUrl: vi.fn(() => '/api/memory/export'),
    getSecuritySettings: vi.fn(async () => ({
      approval_profile: 'strict',
      sandbox_enabled: false,
    })),
    saveSecuritySettings: vi.fn(async () => ({
      approval_profile: 'strict',
      sandbox_enabled: false,
    })),
  }
})

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) =>
        opts?.returnObjects ? [] : opts ? `${k} ${JSON.stringify(opts)}` : k,
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

import SettingsPanel from './SettingsPanel'
import { handFocusBack } from '@/hooks/useFocusReturn'

beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
})

/** The shell the sheet closes onto: the rail button that opened it, and the primary
 *  action `STABLE_FOCUS_TARGETS` resolves to when there is no invoker. */
function Shell({ invokerInert = false }: { invokerInert?: boolean }) {
  return (
    <>
      <div data-testid="rail" inert={invokerInert}>
        <button data-testid="invoker">Einstellungen &amp; Profil</button>
      </div>
      <textarea id="ephe-chat-input" data-testid="chat-input" />
    </>
  )
}

const sheet = (isOpen: boolean) => (
  <>
    <Shell />
    <SettingsPanel isOpen={isOpen} onClose={vi.fn()} initialTab="engine" />
  </>
)

describe('the settings close, both directions', () => {
  it('a close with nothing recorded lands on the stable target and keeps focus off <body>', async () => {
    // The production shape: mounted by the open, so the recorder never saw the press.
    const { rerender } = render(sheet(true))
    const page = await screen.findByTestId('settings-page')
    await vi.waitFor(() => expect(page.contains(document.activeElement)).toBe(true))
    expect(document.activeElement).toBe(screen.getByTestId('settings-back'))

    rerender(sheet(false))

    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByTestId('chat-input')))
    expect(document.activeElement).not.toBe(document.body)
  })

  it('the same close with a recorded invoker lands on the invoker', async () => {
    const { rerender } = render(sheet(false))
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.focusIn(invoker)

    rerender(sheet(true))
    const page = await screen.findByTestId('settings-page')
    await vi.waitFor(() => expect(page.contains(document.activeElement)).toBe(true))

    rerender(sheet(false))

    await vi.waitFor(() => expect(document.activeElement).toBe(invoker))
    expect(invoker.hasAttribute('inert')).toBe(false)
  })

  it('an invoker under a subtree that stayed inert is passed over for the stable target', async () => {
    // Another surface holds the rail inert: handing focus there would be swallowed,
    // which is the condition `usableInvoker` rejects. The sheet's own inert walk
    // leaves an already-inert sibling alone, so this one survives the release.
    const { rerender } = render(
      <>
        <Shell invokerInert />
        <SettingsPanel isOpen={false} onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.focusIn(invoker)
    expect(invoker.closest('[inert]')).not.toBeNull()

    rerender(
      <>
        <Shell invokerInert />
        <SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    const page = await screen.findByTestId('settings-page')
    await vi.waitFor(() => expect(page.contains(document.activeElement)).toBe(true))

    rerender(
      <>
        <Shell invokerInert />
        <SettingsPanel isOpen={false} onClose={vi.fn()} initialTab="engine" />
      </>,
    )

    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByTestId('chat-input')))
    expect(invoker.closest('[inert]')).not.toBeNull()
    expect(document.activeElement).not.toBe(invoker)
  })
})

describe('handFocusBack rejects an invoker that cannot take focus', () => {
  it('the body is never handed focus', async () => {
    // The capture side would never record the body, so the check is called directly:
    // a handback that resolves to the body is the defect this contract removes.
    const target = document.createElement('textarea')
    target.id = 'ephe-chat-input'
    document.body.appendChild(target)

    handFocusBack(document.body)

    await vi.waitFor(() => expect(document.activeElement).toBe(target))
    expect(document.activeElement).not.toBe(document.body)
  })

  it('a detached invoker is never handed focus either', async () => {
    const gone = document.createElement('button')
    document.body.appendChild(gone)
    gone.remove()
    const target = document.createElement('textarea')
    target.id = 'ephe-chat-input'
    document.body.appendChild(target)

    handFocusBack(gone)

    await vi.waitFor(() => expect(document.activeElement).toBe(target))
    expect(document.activeElement).toBe(target)
  })
})
