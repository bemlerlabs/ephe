/**
 * A restored session carries its rows from the server mirror, and that projection
 * writes role/content/timestamp plus the optional payloads and no message id
 * (server/routes/session_mirror.py:229-249). Measured 2026-10-13 over the machine's
 * own store: 72 non-empty ~/.ephe/sessions/pwa-*.json files hold 298 message rows,
 * 298 of them id-less. The virtual list keyed every row `key={msg.id}`, so the first
 * paint of a restored chat logged "Encountered two children with the same key" —
 * two rows, one key. A console warning on the boot path is how a real error gets
 * learned as noise.
 *
 * The real restore path runs here: only the network edges are mocked, `@/lib/api`
 * hands back the mirror shape that the machine's files hold, and `@/lib/restore`
 * maps it into the store the list reads. The assertion is the warning itself.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, waitFor, cleanup } from '@testing-library/react'

const restoreMock = vi.hoisted(() => ({
  sessions: [] as unknown[],
}))

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () => [],
  dbDeleteSession: async () => {},
  dbSaveSession: async () => {},
  debouncedSaveSession: async () => {},
  flushPendingSave: async () => {},
  dbGetCheckpoints: async () => [],
  dbSaveCheckpoints: async () => {},
}))

vi.mock('@/lib/sessionSync', () => ({
  isSessionSyncEnabled: () => false,
  isTombstoned: () => false,
  queueSessionSync: () => {},
  queueSessionDeleted: () => {},
  flushSessionSync: async () => {},
  MAX_SESSIONS_PER_CALL: 50,
}))

vi.mock('@/lib/api', () => ({
  restoreSessions: async () => ({ sessions: restoreMock.sessions }),
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
  updateSettings: vi.fn(async () => ({})),
  getContextBudget: vi.fn(async () => ({
    message_count: 0,
    char_count: 0,
    estimated_tokens: 0,
    window_tokens: 8192,
    percent: 0,
    compaction_threshold: 28,
    compaction_active: false,
  })),
  getContextStages: vi.fn(async () => ({ stages: [] })),
  getLearningProposals: vi.fn(async () => ({ proposals: [] })),
  acceptLearningProposal: vi.fn(async () => ({ ok: true })),
  dismissLearningProposal: vi.fn(async () => ({ ok: true })),
  getMemoryStats: vi.fn(async () => ({ entries: 0 })),
  listGitBranches: vi.fn(async () => ({ branches: [], current: '' })),
  checkoutGitBranch: vi.fn(async () => ({ ok: true })),
  listSchedules: () => Promise.resolve({ jobs: [] }),
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
      engine_online: true,
      active_provider: 'local_ollama',
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
      context_window: 8192,
    }),
  setModelProvider: vi.fn(() => Promise.resolve({ active: { type: 'local_ollama' } })),
  getCellLife: vi.fn(async () => ({ cell: { alive: false, calls: 0, avg_ms: null } })),
  getTrajectory: vi.fn(async () => ({ steps: [] })),
  getTasks: vi.fn(async () => []),
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
  searchMemory: vi.fn(async () => ({ results: [], total: 0 })),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  importMemory: vi.fn(async () => ({ imported: 0, total: 0 })),
  exportMemoryUrl: vi.fn(() => '/api/memory/export'),
  artifactExportUrl: vi.fn(() => '/api/artifacts/export'),
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      entries: [],
    }),
  getMobileQR: vi.fn(async () => ({
    url: 'http://x/mobile.html',
    qr_base64: 'QUJD',
    mode: 'lan',
    is_public: false,
    requires_internet: false,
    lan_reachable: true,
    message: '',
  })),
  getMobileStatus: vi.fn(async () => ({ connected: false })),
}))

vi.mock('@/lib/stream', () => ({
  streamChat: () => new Promise<void>(() => {}),
  StreamChatError: class StreamChatError extends Error {},
}))

vi.mock('@/hooks/useTauriWindow', () => ({
  useTauriWindow: () => ({ isTauri: false, minimize: () => {}, maximize: () => {} }),
}))

vi.mock('@/hooks/useTauriTray', () => ({ useTauriTray: () => ({ windowVisible: true }) }))

vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}·${JSON.stringify(opts)}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

import ChatLayout from '@/components/dashboard/ChatLayout'
import { messageRowKey } from './index'
import { useChatStore } from '@/store/chatStore'
import type { Session } from '@/types'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/** One mirrored session exactly as session_mirror.py writes it: no message id. */
function mirrorSession() {
  return {
    id: 'restored-1',
    title: 'Restored chat',
    updated_at: 1759750010000,
    created_at: 1759750000000,
    messages: [
      { role: 'user', content: 'restored prompt', timestamp: 1759750001000 },
      { role: 'assistant', content: 'restored answer', timestamp: 1759750010000 },
    ],
  }
}

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
  for (const prop of ['offsetHeight', 'clientHeight'] as const) {
    Object.defineProperty(HTMLElement.prototype, prop, {
      configurable: true,
      get() {
        return this.classList.contains('overflow-y-auto') ? 600 : 0
      },
    })
  }
  restoreMock.sessions = [mirrorSession()]
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    currentSession: null,
    hydrated: false,
    isTyping: false,
    pendingToolCall: null,
    checkpoints: {},
  })
})

afterEach(() => {
  cleanup()
  restoreMock.sessions = []
})

describe('a restored, id-less chat', () => {
  it('renders its rows without the duplicate-key warning', async () => {
    const logged: string[] = []
    const spy = vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      logged.push(args.map((a) => String(a)).join(' '))
    })

    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(
        document.querySelectorAll('[data-testid="message-row"]').length,
      ).toBeGreaterThanOrEqual(2),
    )

    const keyWarnings = logged.filter((line) => /key/i.test(line))
    expect(keyWarnings).toEqual([])
    spy.mockRestore()
  })

  it('hands the store rows whose ids are defined and unique', async () => {
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    await waitFor(() => expect(useChatStore.getState().sessions.length).toBe(1))

    const rows = (useChatStore.getState().sessions[0] as Session).messages
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(typeof row.id).toBe('string')
      expect(row.id.length).toBeGreaterThan(0)
    }
    expect(new Set(rows.map((r) => r.id)).size).toBe(rows.length)
  })
})

describe('the row key is total', () => {
  it('names an id-less row by its index, so no two rows share a key', () => {
    const keys = [0, 1, 2].map((index) => messageRowKey({}, index))
    expect(new Set(keys).size).toBe(3)
    for (const key of keys) expect(key.length).toBeGreaterThan(0)
  })

  it('keeps the id of a row that carries one', () => {
    expect(messageRowKey({ id: 'u-1' }, 4)).toBe('u-1')
  })

  it('the list builds its keys with this function, never with msg.id alone', () => {
    const source = readFileSync(
      join(process.cwd(), 'src/components/dashboard/chat/index.tsx'),
      'utf8',
    )
    expect(source).toContain('key={messageRowKey(msg, virtualItem.index)}')
    expect(source).not.toContain('key={msg.id}')
  })
})
