// W44 P1b — contextWindow gets re-fetched after a model/provider switch.
// The fetch originally hung on an empty dependency list (mount only), so the
// context window stuck to the old value after the model had changed.
// Pattern: the window event 'ephe:model-changed' is the re-fetch trigger.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, waitFor } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'

const providerState = vi.hoisted(() => ({ window: 262998, calls: 0 }))

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
  providerState.window = 262998
  providerState.calls = 0
})

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: () => Promise.resolve([]),
  dbDeleteSession: () => {},
  debouncedSaveSession: () => {},
  flushPendingSave: () => {},
  dbGetCheckpoints: () => Promise.resolve([]),
  dbSaveCheckpoints: () => {},
}))
vi.mock('@/lib/api', () => ({
  // WP5: ChatLayout pulls CellLifeLine in now — without this value the row fetches into nothing.
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
  updateSettings: vi.fn(async () => ({})),
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
  getModelProviders: () => {
    providerState.calls += 1
    return Promise.resolve({
      active: { type: 'local_ollama', model: 'gemma4:12b', offline_capable: true },
      providers: [],
      local_models: [],
      local_model_options: [],
      context_window: providerState.window,
    })
  },
  setModelProvider: vi.fn(() =>
    Promise.resolve({ active: { type: 'local_ollama', model: 'gemma4:12b' } }),
  ),
}))
vi.mock('@/lib/stream', () => ({
  streamChat: () => new Promise<void>(() => {}),
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

describe('ChatLayout contextWindow re-fetch (W44 P1b)', () => {
  it('re-fetches the context window after a model-change event', async () => {
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    // the mount fetch has gone through.
    await waitFor(() => {
      expect(providerState.calls).toBeGreaterThanOrEqual(1)
    })
    const afterMount = providerState.calls
    // A model/provider switch fires the event — the meter has to read the window again.
    providerState.window = 8192
    window.dispatchEvent(new CustomEvent('ephe:model-changed'))
    await waitFor(() => {
      expect(providerState.calls).toBeGreaterThan(afterMount)
    })
  })
})
