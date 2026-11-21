/**
 * A2 — on macOS the native traffic lights are the only window buttons. The
 * header overflow used to carry a second minimize/maximize pair on every Tauri
 * platform, including the one whose title bar already draws three.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, fireEvent } from '@testing-library/react'

const platform = vi.hoisted(() => ({ mac: true }))

vi.mock('@/lib/shortcuts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/shortcuts')>()
  return { ...actual, isMacPlatform: () => platform.mac }
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
  getTrajectory: vi.fn(async () => ({ turns: [] })),
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
  listMemory: () => Promise.resolve({ entries: [], total: 0 }),
  getPackIndex: () => Promise.resolve({ version: 1, packs: [] }),
  getSchedulePresets: () => Promise.resolve({ presets: [] }),
  getScheduleResults: () => Promise.resolve({ results: [] }),
  getContextBudget: () =>
    Promise.resolve({
      message_count: 0,
      char_count: 0,
      estimated_tokens: 0,
      window_tokens: 8192,
      percent: 0,
      compaction_threshold: 28,
      compaction_active: false,
    }),
  listSchedules: () => Promise.resolve({ jobs: [] }),
  getTasks: () => Promise.resolve([]),
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
}))
vi.mock('@/hooks/useTauriWindow', () => ({
  useTauriWindow: () => ({
    isTauri: true,
    minimize: vi.fn(),
    maximize: vi.fn(),
    close: vi.fn(),
    show: vi.fn(),
    hide: vi.fn(),
  }),
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

import ChatLayout from '@/components/dashboard/ChatLayout'

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
})

async function openOverflow() {
  const more = await screen.findByTestId('header-more')
  more.focus()
  fireEvent.keyDown(more, { key: 'Enter' })
  await screen.findByTestId('header-new-session')
}

function renderShell() {
  return render(
    <MemoryRouter>
      <ChatLayout />
    </MemoryRouter>,
  )
}

describe('header window controls per platform', () => {
  it('leaves the native traffic lights as the only window-button group on macOS', async () => {
    platform.mac = true
    renderShell()
    await openOverflow()
    expect(screen.queryByTestId('header-minimize')).toBeNull()
    expect(screen.queryByTestId('header-maximize')).toBeNull()
  })

  it('keeps the minimize/maximize menu items unchanged on Windows and Linux', async () => {
    platform.mac = false
    renderShell()
    await openOverflow()
    const minimize = screen.getByTestId('header-minimize')
    const maximize = screen.getByTestId('header-maximize')
    expect(minimize.getAttribute('role')).toBe('menuitem')
    expect(maximize.getAttribute('role')).toBe('menuitem')
    expect(minimize.textContent).toContain('nav.minimize')
    expect(maximize.textContent).toContain('nav.maximize')
  })
})
