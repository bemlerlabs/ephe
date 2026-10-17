// WD-28: keyboard-only walkthrough of the settings dialog. No pointer anywhere —
// the walk presses Tab/Shift+Tab and nothing else, and checks that the focus runs
// the full order, never leaves the dialog, and that a save from the keyboard keeps
// the focus inside it (it used to land on <body> the moment the button gave way to
// the confirmation, leaving the trap without a boundary to hold).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getSettings: vi.fn(async () => ({
      provider: { type: 'openai_compatible', model: 'gemma4:12b', endpoint: 'http://x/v1' },
      memory_enabled: true,
      language: 'de',
      theme: 'dark',
    })),
    updateSettings: vi.fn(async () => ({})),
    healthCheck: vi.fn(async () => ({ ollama: false, models: [], active_tier: 'power' })),
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
      path: '/x/hooks.json',
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
      t: (k: string, opts?: Record<string, unknown>) => (opts?.returnObjects ? [] : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

import SettingsPanel from './SettingsPanel'

// The same definition the dialog uses for "a tab stop" (model/useSettingsState).
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

const label = (el: Element | null) =>
  el
    ? `${el.tagName.toLowerCase()}:${
        el.getAttribute('data-testid') ??
        el.getAttribute('aria-label') ??
        (el as HTMLElement).className.slice(0, 24)
      }`
    : 'NULL'

/** The browser's own Tab: fire the keydown (so the dialog's trap can intercept),
 *  otherwise move to the next focusable — jsdom does not move the focus itself. */
function pressTab(page: HTMLElement, shift: boolean): string {
  const from = document.activeElement as HTMLElement
  fireEvent.keyDown(from, { key: 'Tab', shiftKey: shift })
  if (!page.contains(document.activeElement)) return 'OUTSIDE'
  if (document.activeElement !== from) return label(document.activeElement)
  const list = Array.from(page.querySelectorAll<HTMLElement>(FOCUSABLE))
  const next = list[list.indexOf(from) + (shift ? -1 : 1)]
  if (next) next.focus()
  return page.contains(document.activeElement) ? label(document.activeElement) : 'OUTSIDE'
}

async function openPanel(onClose = vi.fn()) {
  render(<SettingsPanel isOpen onClose={onClose} initialTab="engine" />)
  const page = await screen.findByTestId('settings-page')
  await screen.findByTestId('settings-save')
  return page
}

beforeEach(() => localStorage.clear())

describe('settings keyboard-only walkthrough (no pointer)', () => {
  it('opens on the first stop and walks the whole order back to it', async () => {
    const page = await openPanel()
    const first = page.querySelector<HTMLElement>(FOCUSABLE)!
    await waitFor(() => expect(document.activeElement).toBe(first))
    expect(label(first)).toBe('button:settings-back')

    const order = Array.from(page.querySelectorAll<HTMLElement>(FOCUSABLE)).map(label)
    expect(order.length).toBeGreaterThan(10)

    const seen = [label(document.activeElement)]
    for (let i = 0; i < order.length; i++) seen.push(pressTab(page, false))

    // Every stop in DOM order, and the last one wraps back onto the first.
    expect(seen.slice(0, order.length)).toEqual(order)
    expect(seen[order.length]).toBe(order[0])
    expect(seen).not.toContain('OUTSIDE')
    expect(seen).not.toContain('NULL')
  })

  it('holds the focus inside the dialog at both ends', async () => {
    const page = await openPanel()
    const list = Array.from(page.querySelectorAll<HTMLElement>(FOCUSABLE))
    const first = list[0]!
    const last = list[list.length - 1]!
    expect(label(last)).toBe('button:settings-save')

    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(document.activeElement).toBe(first)

    first.focus()
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  it('keeps the focus inside the dialog after a save from the keyboard', async () => {
    const page = await openPanel()
    const save = await screen.findByTestId('settings-save')
    save.focus()
    expect(document.activeElement).toBe(save)

    // Enter on a focused button reaches the page as a click; jsdom does not
    // synthesise that click, so the one the browser would fire is sent here.
    fireEvent.keyDown(save, { key: 'Enter' })
    fireEvent.click(save)

    const done = await screen.findByTestId('settings-saved')
    expect(done.getAttribute('role')).toBe('status')
    expect(page.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).toBe(done)

    // When the confirmation gives way to the button again, focus stays inside too.
    await waitFor(() => expect(screen.queryByTestId('settings-save')).toBeTruthy(), {
      timeout: 3000,
    })
    // Focus returns a tick after the swap, and under load that tick stretches. The
    // invariant is that focus lands inside the page, so wait for it rather than
    // sampling the instant the button reappears.
    await waitFor(() => expect(page.contains(document.activeElement)).toBe(true), {
      timeout: 3000,
    })
  })
})
