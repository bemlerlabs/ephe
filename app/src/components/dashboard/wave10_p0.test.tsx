/**
 * Wave 10 · P0 UI batch (DCR audit consolidation):
 *  P0-2  the header toggles must already be visible from md (iPad portrait 768px).
 *  P0-3  the settings fields need the unified focus ring (WCAG 2.4.7).
 *
 * jsdom does not evaluate media queries — assert on the className strings
 * (the same convention as the k1/k2/k3 parity tests).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, waitFor } from '@testing-library/react'

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
  dbGetCheckpoints: () => Promise.resolve([]),
  dbSaveCheckpoints: () => {},
}))
vi.mock('@/lib/api', () => ({
  // WP5: ChatLayout pulls in CellLifeLine now — without this value the row fetches into nothing.
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
  searchMemory: vi.fn(async () => ({ results: [], total: 0 })),
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
    useTranslation: () => ({
      t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

import ChatLayout from '@/components/dashboard/ChatLayout'
import SettingsPanel from '@/components/dashboard/SettingsPanel'

describe('Welle10 P0-2 — Header-Toggles ab md', () => {
  it('Sidebar-, Panel- und Library-Toggle nutzen md: als Untergrenze (kein lg:)', () => {
    const { container } = render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    const ids = ['header-sidebar-toggle', 'side-panel-toggle', 'artifact-library-toggle']
    for (const id of ids) {
      const el = container.querySelector(`[data-testid="${id}"]`)
      expect(el, id).toBeTruthy()
      const cls = String((el as Element).className)
      expect(cls, id).toMatch(/(^|\s)md:inline-flex(\s|$)/)
      expect(cls, id).not.toMatch(/(^|\s)lg:inline-flex(\s|$)/)
    }
  })

  it('Hamburger traegt md:hidden (sichtbar ab md), kein lg:hidden', () => {
    const { container } = render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    const buttons = Array.from(container.querySelectorAll('button'))
    const burger = buttons.find((b) => /(^|\s)md:hidden(\s|$)/.test(String(b.className)))
    expect(burger, 'kein Button mit md:hidden (Hamburger)').toBeTruthy()
    expect(String(burger!.className)).not.toMatch(/(^|\s)lg:hidden(\s|$)/)
  })
})

describe('Welle10 P0-3 — Fokus-Ring in den Settings', () => {
  it('alle Text-Inputs/Selects der Settings tragen outline + focus-visible-Ring-Klassen', async () => {
    const { container } = render(<SettingsPanel isOpen onClose={vi.fn()} />)
    let fields: Element[] = []
    await waitFor(() => {
      fields = Array.from(
        container.querySelectorAll('input:not([type="hidden"]), textarea, select'),
      )
      expect(fields.length).toBeGreaterThan(0)
    })
    const missing = fields
      .filter((f) => !/(^|\s)(focus-visible:outline-2|focus-ring)(\s|$)/.test(String(f.className)))
      .map((f) => f.getAttribute('data-testid') || f.getAttribute('id') || f.tagName)
    expect(missing).toEqual([])
  })
})
