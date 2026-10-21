/**
 * W3-57 — the full keyboard path through the main surfaces.
 *
 * GIVEN  the shell (ChatLayout) is up with reachable header meta (the git branch)
 * WHEN   it is driven by keyboard alone
 * THEN   every main surface (#main-content, composer, header, toolbar,
 *        shortcut overlay, branch menu) carries a focusable, named target
 * AND    the branch menu is a real menu (role=menu/menuitem, arrow roving),
 *        Escape closes ONLY the menu and returns focus to the trigger,
 *        Tab closes it without trapping focus inside.
 *
 * No other wave's values are pinned here: only the keyboard-visible
 * contracts of the shell (roles, names, focus order).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'

// The header's git meta goes through a raw fetch('/api/git/info'), bypassing @/lib/api.
const GIT_INFO = { workspace: '/tmp/ws', git: true, branch: 'main', dirty: 0 }

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
  // jsdom has no matchMedia (Sidebar → useMediaQuery)
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (q: string) => ({
      matches: false,
      media: q,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  })
  const patchHeight = (prop: 'offsetHeight' | 'clientHeight') => {
    Object.defineProperty(HTMLElement.prototype, prop, {
      configurable: true,
      get() {
        return this.classList.contains('overflow-y-auto') ? 600 : 0
      },
    })
  }
  patchHeight('offsetHeight')
  patchHeight('clientHeight')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      String(url).includes('/api/git/info')
        ? { ok: true, json: async () => GIT_INFO }
        : { ok: false, json: async () => ({}) },
    ),
  )
})

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: () => Promise.resolve([]),
  dbDeleteSession: () => {},
  debouncedSaveSession: () => {},
  dbGetCheckpoints: () => Promise.resolve([]),
  dbSaveCheckpoints: () => {},
}))
vi.mock('@/lib/api', () => ({
  getCellLife: vi.fn(async () => ({ cell: { alive: false, calls: 0, avg_ms: null } })),
  getSetupStatus: () =>
    Promise.resolve({
      configured: true,
      provider: 'local_ollama',
      model: null,
      url: null,
      reachable: true,
      available_models: [],
    }),
  getSettings: () => Promise.resolve({ provider: { type: 'local_ollama', model: 'gemma4:12b' } }),
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      workspace_set: true,
      entries: [],
    }),
  updateSettings: vi.fn(async () => ({
    provider: {},
    memory_enabled: true,
    language: 'en',
    theme: 'forest',
  })),
  listProjects: () => Promise.resolve({ workspace: '/tmp/ws', projects: [], generated_at: '' }),
  listArtifacts: () => Promise.resolve({ artifacts: [], total: 0 }),
  listSkills: () => Promise.resolve({ skills: [], total: 0 }),
  installSkill: vi.fn(async () => ({ installed: [], updated: [], skipped: [] })),
  disableSkill: vi.fn(async () => ({ name: '', disabled: false })),
  enableSkill: vi.fn(async () => ({ name: '', disabled: false })),
  deleteSkill: vi.fn(async () => ({ deleted: '' })),
  getImageSettings: vi.fn(async () => ({
    base_url: '',
    model: '',
    has_api_key: false,
    api_key_hint: '',
  })),
  getPackIndex: vi.fn(async () => ({ version: 1, packs: [] })),
  getSchedulePresets: vi.fn(async () => ({ presets: [] })),
  getScheduleResults: vi.fn(async () => ({ results: [] })),
  runScheduleJob: vi.fn(async () => ({
    job_id: '',
    task: '',
    executed_at: '',
    result: '',
    error: null,
  })),
  listMemory: vi.fn(async () => ({ entries: [], total: 0 })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  importMemory: vi.fn(async () => ({ imported: 0, total: 0 })),
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
  artifactExportUrl: vi.fn(() => '/api/artifacts/export'),
  getContextBudget: vi.fn(async () => ({
    message_count: 0,
    char_count: 0,
    estimated_tokens: 0,
    window_tokens: 8192,
    percent: 0,
    compaction_threshold: 28,
    compaction_active: false,
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
  listSchedules: () => Promise.resolve({ jobs: [] }),
  getTasks: () => Promise.resolve([]),
  createSchedule: () => Promise.resolve({ job_id: 'x', message: 'ok' }),
  deleteSchedule: () => Promise.resolve({ status: 'ok', job_id: 'x' }),
  approveSandbox: () => Promise.resolve({ status: 'ok' }),
  healthCheck: () =>
    Promise.resolve({
      status: 'ok',
      ollama: true,
      models: [],
      active_tier: 'offline',
      active_model: 'x',
      dgx_online: false,
      offline_capable: true,
      requires_internet: false,
    }),
  getModelProviders: () =>
    Promise.resolve({
      active: { type: 'local_ollama', model: 'gemma4:12b', offline_capable: true },
      providers: [],
      local_models: [],
      local_model_options: [],
      context_window: null,
    }),
  setModelProvider: vi.fn(() =>
    Promise.resolve({ active: { type: 'local_ollama', model: 'gemma4:12b' } }),
  ),
  // Header-Zweig-Chip: die Liste, die das Menü rendert.
  listGitBranches: vi.fn(async () => ({ branches: ['main', 'feature/x'], current: 'main' })),
  checkoutGitBranch: vi.fn(async () => ({ ok: true, branch: 'feature/x' })),
}))
vi.mock('@/lib/stream', () => ({
  streamChat: () => new Promise(() => {}),
  StreamChatError: class StreamChatError extends Error {},
}))
vi.mock('@/hooks/useTauriWindow', () => ({
  useTauriWindow: () => ({ isTauri: false, minimize: () => {}, maximize: () => {} }),
}))
vi.mock('@/hooks/useTauriTray', () => ({ useTauriTray: () => ({ windowVisible: true }) }))
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
      i18n: { language: 'en' },
    }),
  }
})

function renderShell() {
  return render(
    <MemoryRouter>
      <ChatLayout />
    </MemoryRouter>,
  )
}

async function openBranchMenu() {
  const trigger = await screen.findByTestId('header-branch-chip')
  fireEvent.click(trigger)
  const menu = await screen.findByTestId('branch-menu')
  const items = await screen.findAllByRole('menuitem')
  return { trigger, menu, items }
}

describe('W3-57 — Tastaturpfad durch die Hauptflächen (ChatLayout)', () => {
  it('the skip target #main-content is focusable and the composer is named', async () => {
    renderShell()
    const main = await waitFor(() => {
      const el = document.getElementById('main-content')
      expect(el).toBeTruthy()
      return el as HTMLElement
    })
    expect(main.getAttribute('tabindex')).toBe('-1')
    main.focus()
    expect(document.activeElement).toBe(main)

    const composer = document.getElementById('ephe-chat-input') as HTMLTextAreaElement | null
    expect(composer).toBeTruthy()
    expect(composer!.getAttribute('aria-label')).toBeTruthy()
  })

  it('the header keeps named buttons; the overflow holds named menuitems', async () => {
    renderShell()
    for (const id of [
      'header-sidebar-toggle',
      'header-menu-toggle',
      'side-panel-toggle',
      'header-more',
    ]) {
      const el = await screen.findByTestId(id)
      expect(el.tagName, id).toBe('BUTTON')
      const name = el.getAttribute('aria-label')?.trim() || el.textContent?.trim()
      expect(name, id).toBeTruthy()
    }
    const more = await screen.findByTestId('header-more')
    more.focus()
    fireEvent.keyDown(more, { key: 'Enter' })
    for (const id of ['header-new-session', 'header-update', 'header-help']) {
      const el = await screen.findByTestId(id)
      expect(el.getAttribute('role'), id).toBe('menuitem')
      expect(el.textContent?.trim(), id).toBeTruthy()
    }
  })

  it('Zweig-Menü: role=menu/menuitem, Fokus springt hinein, Pfeile wandern, Escape gibt den Fokus zurück', async () => {
    renderShell()
    const { trigger, menu, items } = await openBranchMenu()

    // Menü-Semantik + Verknüpfung am Auslöser
    expect(menu.getAttribute('role')).toBe('menu')
    expect(menu.getAttribute('aria-label')).toBe('header.branches')
    expect(trigger.getAttribute('aria-haspopup')).toBe('menu')
    expect(trigger.getAttribute('aria-controls')).toBe('branch-menu')
    expect(items.length).toBeGreaterThanOrEqual(2)
    for (const item of items) {
      expect(item.getAttribute('role')).toBe('menuitem')
      expect(item.getAttribute('tabindex')).toBe('-1')
    }

    // Focus moves into the menu on its own (the branch list arrives async).
    await waitFor(() => expect(document.activeElement).toBe(items[0]))

    // Roving with arrows / Home / End: no tab stop per entry.
    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])
    fireEvent.keyDown(menu, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(items[0])
    fireEvent.keyDown(menu, { key: 'End' })
    expect(document.activeElement).toBe(items[items.length - 1])
    fireEvent.keyDown(menu, { key: 'Home' })
    expect(document.activeElement).toBe(items[0])

    // Escape closes ONLY the menu and hands focus to the trigger.
    fireEvent.keyDown(menu, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('branch-menu')).toBeNull())
    expect(document.activeElement).toBe(trigger)
  })

  it('Tab schließt das Zweig-Menü, statt den Fokus darin zu fangen', async () => {
    renderShell()
    const { menu } = await openBranchMenu()
    fireEvent.keyDown(menu, { key: 'Tab' })
    await waitFor(() => expect(screen.queryByTestId('branch-menu')).toBeNull())
  })

  it('Hilfe öffnet die Shortcut-Übersicht als modalen Dialog; Escape schließt sie', async () => {
    renderShell()
    const more = await screen.findByTestId('header-more')
    more.focus()
    fireEvent.keyDown(more, { key: 'Enter' })
    const help = await screen.findByTestId('header-help')
    help.focus()
    fireEvent.keyDown(help, { key: 'Enter' })
    const overlay = await screen.findByTestId('shortcuts-overlay')
    expect(overlay.getAttribute('role')).toBe('dialog')
    expect(overlay.getAttribute('aria-modal')).toBe('true')

    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('shortcuts-overlay')).toBeNull())
  })
})
