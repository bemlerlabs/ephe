import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'
import { useChatStore } from '@/store/chatStore'

const streamState = vi.hoisted(() => ({ mode: 'hang' as 'hang' | 'reply' | 'partial' }))
const dbState = vi.hoisted(() => ({ flushes: 0 }))

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
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
})

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: () => Promise.resolve([]),
  dbDeleteSession: () => {},
  debouncedSaveSession: () => {},
  flushPendingSave: () => {
    dbState.flushes += 1
  },
  dbGetCheckpoints: () => Promise.resolve([]),
  dbSaveCheckpoints: () => {},
}))
vi.mock('@/lib/api', () => ({
  // WP5: ChatLayout now pulls CellLifeLine — without this value the row fetches into nothing.
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
}))
// Mirror of the real stream contract: abort → resolve WITHOUT throwing.
vi.mock('@/lib/stream', () => ({
  streamChat: (
    _payload: unknown,
    opts?: { signal?: AbortSignal; onEvent?: (e: { type: string; data?: string }) => void },
  ) =>
    new Promise<void>((resolve) => {
      const onAbort = () => resolve()
      opts?.signal?.addEventListener('abort', onAbort)
      if (streamState.mode === 'reply') {
        setTimeout(() => {
          opts?.signal?.removeEventListener('abort', onAbort)
          opts?.onEvent?.({ type: 'chunk', data: 'second-reply' })
          opts?.onEvent?.({ type: 'done' })
          resolve()
        }, 0)
      }
      if (streamState.mode === 'partial') {
        // One chunk arrives, then the stream hangs until the stop click.
        setTimeout(() => opts?.onEvent?.({ type: 'chunk', data: 'partial-antwort text' }), 0)
      }
    }),
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
    useTranslation: () => ({
      t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
      i18n: { language: 'en' },
    }),
  }
})

describe('ChatLayout composer mode switch (P4)', () => {
  let cleanup: () => void

  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
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
    const ph = (p: 'offsetHeight' | 'clientHeight') =>
      Object.defineProperty(HTMLElement.prototype, p, {
        configurable: true,
        get() {
          return this.classList.contains('overflow-y-auto') ? 600 : 0
        },
      })
    ph('offsetHeight')
    ph('clientHeight')
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    } as never)
    useChatStore.getState().createSession('Mode-Test')
    cleanup = render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    ).unmount
  })

  afterEach(() => cleanup())

  it('Frische Session startet Full access (Paritaet); Plan-Klick wechselt Chip + session.mode', () => {
    // The default of fresh sessions is a tool-capable mode (DEFAULT_COMPOSER_MODE).
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain('Full access')
    expect(screen.queryByTestId('composer-ask-hint')).toBeNull()
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    fireEvent.click(screen.getByTestId('composer-mode-plan'))
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain('Plan')
    const st = useChatStore.getState()
    expect(st.sessions.find((x) => x.id === st.activeSessionId)?.mode).toBe('plan')
  })
})
