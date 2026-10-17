/**
 * Deploy-check P1-1 regression: pressing Stop must close the aborted turn.
 *
 * Root cause: streamChat resolves NORMALLY after an abort (reader cancel +
 * return) — runTurn's catch never ran, finishTurn() never happened, the
 * aborted bubble stayed streaming:true and the NEXT turn's response was
 * appended into it (appearing BEFORE the second user message in the DOM).
 *
 * GIVEN  a streaming turn that gets stopped before any content arrives
 * WHEN   the empty aborted bubble is dropped and a new message is sent
 * THEN   the new response renders in its OWN bubble AFTER the new user message.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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
  // WP5: ChatLayout pulls CellLifeLine in now — without this value the row fetches into nothing.
  getCellLife: vi.fn(async () => ({ cell: { alive: false, calls: 0, avg_ms: null } })),
  // WP5/replay: the stopped turn's bubble mounts ToolReplayKader, which reads the trajectory.
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  LAN_TOKEN: null,
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
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
        // One chunk arrives, then the stream hangs until the Stop click.
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

const ta = () => screen.getByPlaceholderText('chat.placeholder') as HTMLTextAreaElement

function send(text: string) {
  fireEvent.change(ta(), { target: { value: text } })
  fireEvent.keyDown(ta(), { key: 'Enter' })
}

/** Last assistant message of the active session (lib target < es2022, no .at). */
function lastAssistantMsg() {
  const msgs = useChatStore
    .getState()
    .currentSession!.messages.filter((m) => m.role === 'assistant')
  return msgs[msgs.length - 1]
}

describe('ChatLayout stop handling (deploy-check P1-1)', () => {
  let cleanup: () => void

  beforeEach(() => {
    streamState.mode = 'hang'
    dbState.flushes = 0
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('Stop-Test')
    cleanup = render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    ).unmount
  })

  afterEach(() => {
    cleanup()
  })

  it('stop closes the turn and drops the empty aborted bubble', async () => {
    send('first message')
    await waitFor(() => {
      const s = useChatStore.getState().currentSession
      expect(s?.messages.some((m) => m.role === 'assistant' && m.streaming)).toBe(true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'chat.stop' }))

    await waitFor(() => {
      const s = useChatStore.getState().currentSession
      // Empty aborted bubble is dropped — only the user message remains.
      expect(s?.messages.filter((m) => m.role === 'assistant')).toHaveLength(0)
      expect(useChatStore.getState().isTyping).toBe(false)
    })
  })

  it('next turn after stop renders in its own bubble after the user message', async () => {
    send('first message')
    await waitFor(() => {
      const s = useChatStore.getState().currentSession
      expect(s?.messages.some((m) => m.role === 'assistant' && m.streaming)).toBe(true)
    })
    fireEvent.click(screen.getByRole('button', { name: 'chat.stop' }))
    await waitFor(() => {
      expect(useChatStore.getState().isTyping).toBe(false)
    })

    streamState.mode = 'reply'
    send('second message')

    await waitFor(() => {
      const s = useChatStore.getState().currentSession
      const replies = s?.messages.filter((m) => m.role === 'assistant') ?? []
      expect(replies).toHaveLength(1)
      expect(replies[0]!.content).toBe('second-reply')
      const userMsgs = s?.messages.filter((m) => m.role === 'user') ?? []
      // Response bubble must come AFTER the second user message in the list.
      const replyIdx = s!.messages.findIndex((m) => m.id === replies[0]!.id)
      const user2Idx = s!.messages.findIndex((m) => m.id === userMsgs[1]!.id)
      expect(replyIdx).toBeGreaterThan(user2Idx)
    })
  })

  it('partial bleibt nach Stop erhalten und wird auf Platte geflusht (I6 P2b)', async () => {
    streamState.mode = 'partial'
    send('langs lied')
    await waitFor(() => {
      expect(lastAssistantMsg()?.content).toContain('partial-antwort')
      expect(lastAssistantMsg()?.streaming).toBe(true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'chat.stop' }))

    await waitFor(() => {
      expect(lastAssistantMsg()?.streaming).toBe(false)
    })
    const a = lastAssistantMsg()!
    expect(a.content).toContain('partial-antwort')
    // The central P2b pin: without the flush the debounced write would die in
    // the timer and the reload would find the empty ensure snapshot (data loss).
    expect(dbState.flushes).toBeGreaterThan(0)
  })
})
