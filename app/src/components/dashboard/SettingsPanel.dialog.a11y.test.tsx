// P4 finding 5: the settings screen was a modal trap — role="dialog" with
// aria-modal="false", focus stayed on the hidden sidebar button when it opened,
// the tab cycle covered only the detail column (the back button sat outside)
// and the background stayed operable. This file holds the correction.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const changeLanguage = vi.fn()

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
      i18n: { language: 'de', changeLanguage },
    }),
  }
})

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  localStorage.clear()
  changeLanguage.mockClear()
})

const focusablesIn = (el: HTMLElement) =>
  Array.from(
    el.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  )

describe('Einstellungen sind ein echter modalen Dialog (P4 Befund 5)', () => {
  it('die Vollseite traegt role=dialog + aria-modal=true, die Detail-Spalte ist Region', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    const page = await screen.findByTestId('settings-page')
    expect(page.getAttribute('role')).toBe('dialog')
    expect(page.getAttribute('aria-modal')).toBe('true')
    expect(page.getAttribute('aria-label')).toBe('chat.settings')
    // No second dialog inside the dialog: the column is content, not a modality.
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    const panel = screen.getByTestId('settings-panel')
    expect(panel.getAttribute('role')).toBe('region')
    expect(panel.getAttribute('aria-modal')).toBeNull()
  })

  it('beim Oeffnen liegt der Fokus im Dialog — nicht am verdeckten Ausloeser', async () => {
    const { rerender } = render(
      <>
        <button data-testid="invoker">Einstellungen & Profil</button>
        <SettingsPanel isOpen={false} onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.focusIn(invoker)
    rerender(
      <>
        <button data-testid="invoker">Einstellungen & Profil</button>
        <SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    const page = await screen.findByTestId('settings-page')
    await vi.waitFor(() => expect(page.contains(document.activeElement)).toBe(true))
    expect(document.activeElement).toBe(screen.getByTestId('settings-back'))
  })

  it('der Hintergrund ist inert, solange der Dialog offen ist', async () => {
    const onClose = vi.fn()
    render(
      <>
        <nav data-testid="behind-sidebar">Seitenleiste</nav>
        <SettingsPanel isOpen onClose={onClose} initialTab="engine" />
      </>,
    )
    const page = await screen.findByTestId('settings-page')
    const sidebar = screen.getByTestId('behind-sidebar')
    expect(sidebar.hasAttribute('inert')).toBe(true)
    expect(sidebar.getAttribute('aria-hidden')).toBe('true')
    expect(page.hasAttribute('inert')).toBe(false)
    fireEvent.click(screen.getByTestId('settings-back'))
    expect(onClose).toHaveBeenCalled()
  })

  it('a global live region stays outside the inert subtree', async () => {
    render(
      <>
        <div data-testid="toast-region" data-inert-exempt="" />
        <SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    await screen.findByTestId('settings-page')
    const toasts = screen.getByTestId('toast-region')
    expect(toasts.hasAttribute('inert')).toBe(false)
    expect(toasts.getAttribute('aria-hidden')).toBeNull()
  })

  it('nach dem Schliessen ist der Hintergrund wieder frei und der Fokus beim Ausloeser', async () => {
    const { container, rerender } = render(
      <>
        <button data-testid="invoker">Einstellungen & Profil</button>
        <SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    const invoker = screen.getByTestId('invoker')
    invoker.focus()
    fireEvent.focusIn(invoker)
    await screen.findByTestId('settings-page')
    expect(invoker.hasAttribute('inert')).toBe(true)
    rerender(
      <>
        <button data-testid="invoker">Einstellungen & Profil</button>
        <SettingsPanel isOpen={false} onClose={vi.fn()} initialTab="engine" />
      </>,
    )
    await vi.waitFor(() => expect(document.activeElement).toBe(invoker))
    expect(invoker.hasAttribute('inert')).toBe(false)
    expect(invoker.getAttribute('aria-hidden')).toBeNull()
    expect(container.textContent).toContain('Einstellungen & Profil')
  })

  it('der Tab-Kreis ist im Dialog geschlossen — auch um den Zurueck-Knopf', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    const page = await screen.findByTestId('settings-page')
    await vi.waitFor(() => expect(page.contains(document.activeElement)).toBe(true))
    const list = focusablesIn(page)
    expect(list.length).toBeGreaterThan(3)
    // From the last element Tab wraps back inside the dialog (not into the chat).
    list[list.length - 1]!.focus()
    fireEvent.keyDown(list[list.length - 1]!, { key: 'Tab' })
    expect(document.activeElement).toBe(list[0])
    expect(page.contains(document.activeElement)).toBe(true)
    // And the same backwards, out of the first one.
    list[0]!.focus()
    fireEvent.keyDown(list[0]!, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(list[list.length - 1])
    expect(page.contains(document.activeElement)).toBe(true)
  })

  it('gedaempfter Text in den Einstellungen haelt 4,5:1 auf Papier', async () => {
    render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="engine" />)
    const page = await screen.findByTestId('settings-page')
    const weak = Array.from(
      page.querySelectorAll<HTMLElement>('[class*="text-status-info/"]'),
    ).filter((el) => /(text-status-info\/(50|55|60|65)\b)/.test(el.className))
    expect(weak).toHaveLength(0)
  })
})
