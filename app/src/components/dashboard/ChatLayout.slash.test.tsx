/**
 * G6 — slash commands in the ChatLayout (new registry extension)
 *
 * GIVEN  ChatLayout with /model, /skills, /sessions, /settings
 * WHEN   the command is entered (Enter)
 * THEN   it runs: system message / panel opening
 */
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'
import { useChatStore } from '@/store/chatStore'
import { streamChat } from '@/lib/stream'

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
  streamChat: vi.fn(() => Promise.resolve()),
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

/**
 * Enter a slash command and hand the transcript row it writes over to React.
 *
 * A client command answers out of a floating promise (`getSettings().then(addMessage)`
 * in chat/model.ts), so the store write lands after the keystroke returns. Outside act
 * that write is React's late work and the assertion can only race it by polling. One
 * macrotask tick inside act lands the command's own chain in the same flush, so the
 * assertion afterwards sees the settled row with nothing pending behind it.
 */
async function typeSlash(cmd: string): Promise<void> {
  await act(async () => {
    fireEvent.change(ta(), { target: { value: cmd } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

/**
 * The first transcript row pulls `MessageBubble` in through React.lazy
 * (chat/index.tsx:88) and that chunk carries the markdown pipeline. A slash command is
 * about the message its command writes, so the chunk is settled here, outside the
 * per-test ceiling. Measured 2026-11-23 on the /model test, one command, competing
 * vitest workers varied: unwarmed 478 ms idle, 1775 ms at 12, 2908 ms at 24, 5898 ms at
 * 30 — past the 5000 ms ceiling, where CI read 6028 ms on the same line. Warmed: 422 /
 * 514 / 1184 / 1596 ms.
 */
beforeAll(async () => {
  await import('@/components/dashboard/MessageBubble')
})

describe('ChatLayout slash commands (G6)', () => {
  let cleanup: () => void

  beforeEach(async () => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('Test-Sitzung')
    // ChatLayout mounts into a dozen already-resolved fetch mocks (getCellLife,
    // getSetupStatus, listProjects, healthCheck, …). Each continuation is a state update
    // that lands after render returns, and React counted three "not wrapped in act"
    // blocks per test for it — 15 for the file, none of them about a slash command.
    // The mount waits for one macrotask inside act, so the shell is settled before a
    // command is typed and a test owns no work past its last assertion.
    await act(async () => {
      cleanup = render(
        <MemoryRouter>
          <ChatLayout />
        </MemoryRouter>,
      ).unmount
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('/model shows the system message carrying the model key', async () => {
    await typeSlash('/model')
    expect(screen.getByText('chat.modelNow')).toBeTruthy()
  })

  it('/skills lists the backend skills', async () => {
    await typeSlash('/skills')
    expect(screen.getByText('chat.skillList')).toBeTruthy()
  })

  it('/sessions shows the session list', async () => {
    await typeSlash('/sessions')
    expect(screen.getByText('chat.sessionList')).toBeTruthy()
  })

  it('/settings opens the settings panel', async () => {
    await typeSlash('/settings')
    // The panel is a lazy subtree of its own (chat/panels.tsx:9); the wait here is its
    // mount, which is the claim of this test.
    await waitFor(
      () => {
        expect(screen.getByTestId('settings-panel')).toBeTruthy()
      },
      { timeout: 5000 },
    )
  })

  it('a command the client registry does not know reaches the model', async () => {
    await typeSlash('/plan the release notes')
    // The hand-off is the claim: an unmatched command reaches the model as the text the
    // person typed. Exactly one hand-off, so a stray send from an earlier test in this
    // file lands here as a failure. What travels inside that payload has one home,
    // chat/model.bootRestore.test.tsx:223.
    expect(streamChat).toHaveBeenCalledTimes(1)
    expect(streamChat).toHaveBeenCalledWith(
      expect.objectContaining({ message: '/plan the release notes' }),
      expect.anything(),
    )
  })
})
