/**
 * I6 P3 — composer focus after a session switch (ChatLayout)
 *
 * GIVEN  ChatLayout is rendered
 * WHEN   a new session becomes active (sidebar button or /new)
 * THEN   the caret sits in the chat input without an extra click; mount itself does not focus
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, waitFor, act, fireEvent } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'

// jsdom has no scrollIntoView (ChatLayout calls it in the auto-scroll effect)
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
  // jsdom: the scroll container (virtualizer) needs a height > 0 (offsetHeight),
  // otherwise @tanstack/react-virtual renders no items at all.
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
})

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: () => Promise.resolve([]),
  dbDeleteSession: () => {},
  debouncedSaveSession: () => {},
  dbGetCheckpoints: () => Promise.resolve([]),
  dbSaveCheckpoints: () => {},
}))
vi.mock('@/lib/api', () => ({
  // WP5: ChatLayout pulls CellLifeLine now — without this value the row fetches into nothing.
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
  // R26: WorkspacePicker (topbar + composer chip) + welcome cards + sidebar tree
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
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
  listSkills: () =>
    Promise.resolve({ skills: [{ name: 'pdf-tools', description: 'PDF verarbeiten' }], total: 1 }),
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
}))
vi.mock('@/lib/stream', () => ({
  streamChat: () => new Promise(() => {}),
  StreamChatError: class StreamChatError extends Error {},
}))
vi.mock('@/hooks/useTauriWindow', () => ({
  useTauriWindow: () => ({ isTauri: false, minimize: () => {}, maximize: () => {} }),
}))
vi.mock('@/hooks/useTauriTray', () => ({
  useTauriTray: () => ({ windowVisible: true }),
}))
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    // t returns the key; returnObjects yields [] (i18next contract),
    // so array-consuming UI (securityInfo) does not crash.
    useTranslation: () => ({
      t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
      i18n: { language: 'en' },
    }),
  }
})

// The composer textarea by placeholder (mock t returns the key; the scheduler panel has its own inputs)

// ── I6 P3 (findings line 25): a new session should focus the composer ──
// Reference-client parity: after createSession (sidebar button or /new) the
// caret belongs in the composer without an extra click. Focus fires on the
// ACTIVE-SESSION SWITCH only (mount must not steal focus / pop mobile keyboards).
function seedSessionState() {
  return {
    sessions: [{ id: 'seed-1', title: 'Seed', messages: [], createdAt: 0 }],
    activeSessionId: 'seed-1',
  } as never
}

describe('ChatLayout — Composer-Fokus nach Session-Wechsel (I6)', () => {
  it('fokussiert das Chat-Input, wenn eine neue Sitzung aktiv wird', async () => {
    const { useChatStore } = await import('@/store/chatStore')
    act(() => {
      useChatStore.setState(seedSessionState())
    })
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    expect(document.activeElement).not.toBe(document.getElementById('ephe-chat-input'))
    act(() => {
      useChatStore.getState().createSession()
    })
    expect(useChatStore.getState().activeSessionId).not.toBe('seed-1')
    await waitFor(() => {
      expect(document.activeElement).toBe(document.getElementById('ephe-chat-input'))
    })
  })

  it('beim Mount wird der Composer NICHT automatisch fokussiert', async () => {
    const { useChatStore } = await import('@/store/chatStore')
    act(() => {
      useChatStore.setState(seedSessionState())
    })
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    expect(document.getElementById('ephe-chat-input')).toBeTruthy()
    expect(document.activeElement).not.toBe(document.getElementById('ephe-chat-input'))
  })

  /**
   * Chrome budget: the header keeps identity, the panel toggle and one named
   * overflow; New Session, navigation, update, theme and help are menu items.
   */
  it('header keeps the compact inventory and the overflow carries the tools', async () => {
    const { screen: sc } = await import('@testing-library/react')
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    expect(await sc.findByTestId('header-more')).toBeTruthy()
    expect(await sc.findByTestId('side-panel-toggle')).toBeTruthy()
    const more = sc.getByTestId('header-more')
    more.focus()
    fireEvent.keyDown(more, { key: 'Enter' })
    for (const id of ['header-new-session', 'header-help', 'header-update', 'header-theme']) {
      expect(await sc.findByTestId(id)).toBeTruthy()
    }
  })

  it('chrome budget: the toolbar row is gone and the moved tools wait in the menu', async () => {
    const { screen: sc } = await import('@testing-library/react')
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    expect(await sc.findByTestId('header-more')).toBeTruthy()
    for (const id of [
      'toolbar-row',
      'toolbar-palette',
      'toolbar-files',
      'toolbar-meta',
      'header-update',
      'header-theme',
      'header-help',
      'header-new-session',
      'session-nav-back',
      'artifact-library-toggle',
      'header-palette',
    ]) {
      expect(sc.queryByTestId(id), id).toBeNull()
    }
  })
})
