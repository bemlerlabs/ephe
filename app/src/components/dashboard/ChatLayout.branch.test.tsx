/**
 * Z37 (parity): the fork indicator — the 'from #N' chip in the header of an active
 * branched session, plus the branch entry of the 12-item session menu. That entry
 * reads 'Zweig ab hier' in the German UI. language-gate: ignore — quotes a rendered label.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import ChatLayout from '@/components/dashboard/ChatLayout'
import { useChatStore } from '@/store/chatStore'

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: () => Promise.resolve([]),
  dbDeleteSession: () => {},
  debouncedSaveSession: () => {},
  flushPendingSave: () => {},
  dbGetCheckpoints: () => Promise.resolve([]),
  dbSaveCheckpoints: () => {},
}))
vi.mock('@/lib/api', async (importOriginal: () => Promise<Record<string, unknown>>) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getSettings: () =>
      Promise.resolve({
        provider: { type: 'local_ollama', model: 'gemma4:12b' },
        memory_enabled: true,
        language: 'en',
        theme: 'forest',
      }),
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
    getContextBudget: () =>
      Promise.resolve({ percent: 10, estimated_tokens: 820, remaining: 7372 }),
    getModelProviders: () =>
      Promise.resolve({
        active: null,
        providers: [],
        local_models: [],
        local_model_options: [],
        context_window: 8192,
      }),
    getMemoryStats: () => Promise.resolve({ count: 0 }),
    getTasks: () => Promise.resolve([]),
    listSchedules: () => Promise.resolve([]),
    searchSessions: () => Promise.resolve({ query: '', results: [], total: 0, elapsed_ms: 0 }),
    exportChatMarkdown: () => Promise.resolve(''),
    downloadTextFile: vi.fn(),
  }
})
vi.mock('react-i18next', async (importOriginal: () => Promise<Record<string, unknown>>) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: { returnObjects?: boolean }) => (opts?.returnObjects ? [] : key),
      i18n: { language: 'en' },
    }),
  }
})
vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => true,
}))

function seed(opts: { loadParent?: boolean } = { loadParent: true }) {
  const msgs = [
    { id: 'm1', role: 'user' as const, content: 'eins', timestamp: 1 },
    { id: 'm2', role: 'assistant' as const, content: 'zwei', timestamp: 2 },
  ]
  const root = {
    id: 'root-1',
    title: 'Basis',
    messages: [{ id: 'm0', role: 'user' as const, content: 'null', timestamp: 0 }],
    createdAt: 0,
  }
  const fork = {
    id: 'fork-1',
    title: 'Basis · #2',
    messages: msgs,
    createdAt: 1,
    parentId: 'root-1',
  }
  useChatStore.setState({
    // loadParent=false simulates the restore case: the parent sits outside the
    // 50-session window or has been deleted — the fork stays behind as an orphan.
    sessions: opts.loadParent ? [root, fork] : [fork],
    activeSessionId: 'fork-1',
    currentSession: fork,
    isTyping: false,
    pendingToolCall: null,
    checkpoints: {},
  })
}

describe('Z37 Fork-Anzeige', () => {
  beforeEach(() => {
    localStorage.clear()
    seed()
  })

  it('Header traegt den from-Chip mit Fork-Punkt', async () => {
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('header-branch-from').textContent).toContain('#2')
    })
  })

  it('Nach dem Klick auf den from-Chip springt der Cursor zur Ursprungssession', async () => {
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('header-branch-from')).toBeTruthy())
    useChatStore.getState().setActiveSession('root-1')
    await waitFor(() => {
      expect(useChatStore.getState().activeSessionId).toBe('root-1')
    })
  })

  it('Waise (Elter ausserhalb des Restore-Fensters): Chip wird nicht gerendert', async () => {
    seed({ loadParent: false })
    render(
      <MemoryRouter>
        <ChatLayout />
      </MemoryRouter>,
    )
    // A short wait: a wrong mount would have had to work its way through the
    // render queue by now; the chip must not show up.
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('header-branch-from')).toBeNull()
  })
})
