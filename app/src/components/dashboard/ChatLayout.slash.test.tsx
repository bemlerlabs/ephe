/**
 * G6 — slash commands in the ChatLayout (new registry extension)
 *
 * GIVEN  ChatLayout with /model, /skills, /sessions, /settings
 * WHEN   the command is entered (Enter)
 * THEN   it runs: system message / panel opening
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'
import { useChatStore } from '@/store/chatStore'

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
  // jsdom: a scroll container (Virtualizer) needs height > 0 (offsetHeight),
  // otherwise @tanstack/react-virtual renders no items.
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
  // WP5: ChatLayout renders the CellLifeLine row now — without this value the row fetches into nothing.
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
  // R26: WorkspacePicker (Topbar + Composer-Chip) + Welcome-Cards + Sidebar-Tree
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
    // t returns the key; returnObjects yields [] (the i18next contract), so
    // UI that consumes an array (securityInfo) does not crash.
    useTranslation: () => ({
      t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
      i18n: { language: 'en' },
    }),
  }
})

// Composer textarea addressed by placeholder (mock t returns the key; the Scheduler panel has its own inputs)
const ta = () => screen.getByPlaceholderText('chat.placeholder') as HTMLTextAreaElement

function typeSlash(cmd: string) {
  fireEvent.change(ta(), { target: { value: cmd } })
  fireEvent.keyDown(ta(), { key: 'Enter' })
}

describe('ChatLayout Slash-Commands (G6)', () => {
  let cleanup: () => void

  beforeEach(() => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('Test-Sitzung')
    cleanup = render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    ).unmount
  })

  afterEach(() => {
    cleanup()
  })

  it('/model zeigt die System-Message mit Model-Key', async () => {
    typeSlash('/model')
    await waitFor(() => {
      expect(screen.getByText('chat.modelNow')).toBeTruthy()
    })
  })

  it('/skills listet die Backend-Skills', async () => {
    typeSlash('/skills')
    await waitFor(() => {
      expect(screen.getByText('chat.skillList')).toBeTruthy()
    })
  })

  it('/sessions zeigt die Session-Liste', async () => {
    typeSlash('/sessions')
    await waitFor(() => {
      expect(screen.getByText('chat.sessionList')).toBeTruthy()
    })
  })

  it('/settings öffnet das Einstellungen-Panel', async () => {
    act(() => {
      typeSlash('/settings')
    })
    await waitFor(() => {
      expect(screen.getByTestId('settings-panel')).toBeTruthy()
    })
  })
})
