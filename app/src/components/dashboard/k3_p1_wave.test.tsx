import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

// K3 (2026-09-08): the P1 wave across the parity matrix — Z07 stdout frames
// (growing pre-block), Z08 duration chip, Z09 swarm nest, Z14 sources bar,
// Z24 model chip with dropdown, Z29 terminal recall, Z35 sidebar full-text search.

const apiMocks = vi.hoisted(() => ({
  runShell: vi.fn(async () => ({ command: 'ls', output: 'a\nb', ok: true })),
  runShellPty: vi.fn(async () => ({ command: 'ls', output: 'a\nb', ok: true })),
  proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  getTrajectory: vi.fn(async () => ({ turns: [] })),
  listFs: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'p', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
  synthesizeSpeech: vi.fn(async () => ''),
  fileUrl: vi.fn((p: string) => `/api/file?path=${p}`),
  feedbackThumbsUp: vi.fn(async () => ({ saved: true })),
  feedbackThumbsDown: vi.fn(async () => ({ saved: true })),
  listProjects: vi.fn(async () => ({ workspace: '', projects: [], generated_at: '' })),
  listSchedules: vi.fn(async () => ({ jobs: [] })),
  updateSettings: vi.fn(async () => ({})),
  exportChatMarkdown: vi.fn(async () => '# x'),
  downloadTextFile: vi.fn(),
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'qwen3.8-flash-next' },
    providers: [
      { id: 'local_ollama', label: 'Lokal (Ollama)' },
      { id: 'openai_compatible', label: 'OpenAI-kompatibel' },
    ],
    local_models: ['qwen3.8-flash-next'],
    local_model_options: [],
  })),
  setModelProvider: vi.fn(async () => ({ ok: true })),
  getSetupStatus: vi.fn(async () => ({
    configured: true,
    provider: 'local_ollama',
    model: null,
    url: null,
    reachable: true,
    available_models: [],
  })),
  searchSessions: vi.fn(async () => ({
    query: 'alpha',
    results: [
      {
        session_id: 's1',
        session_title: 'Alpha',
        role: 'user',
        snippet: '…alpha…',
        content: 'alpha',
        updated_at: '',
      },
    ],
    total: 1,
    elapsed_ms: 0.3,
  })),
}))

vi.mock('@/lib/api', () => apiMocks)
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}))

const storeState = vi.hoisted(() => ({
  sessions: [
    {
      id: 's1',
      title: 'Alpha',
      messages: [{ role: 'user', content: 'alpha' }],
      createdAt: Date.now(),
    },
  ] as Array<Record<string, unknown>>,
  activeSessionId: 's1',
  setActiveSession: vi.fn(),
}))
vi.mock('@/store/chatStore', () => ({
  DEFAULT_SESSION_TITLE: 'New Session',
  DEFAULT_COMPOSER_MODE: 'full-access',
  useChatStore: (sel?: (s: Record<string, unknown>) => unknown) => {
    const st: Record<string, unknown> = {
      sessions: storeState.sessions,
      activeSessionId: storeState.activeSessionId,
      setActiveSession: storeState.setActiveSession,
      createSession: vi.fn(),
      deleteSession: vi.fn(),
      renameSession: vi.fn(),
      togglePin: vi.fn(),
    }
    return sel ? sel(st) : st
  },
}))
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => true }))

// P1-5: the terminal tab now defaults to Live (xterm.js). The real
// terminal renderer needs Canvas/WebSocket — irrelevant for the recall
// logic here, so it is mocked as a stub; the history path stays real.
vi.mock('./agent/LiveTerminal', () => ({ default: () => <div data-testid="live-terminal" /> }))

import ActivityFeed from './ActivityFeed'
import ChatInput from './ChatInput'
import Sidebar from './Sidebar'
import AgentPanel from './AgentPanel'
import MessageBubble from './MessageBubble'
import { applyStreamEvent } from '@/lib/streamActions'
import { extractSourceUrls } from '@/lib/toolCardModel'
import type { ChatMessage, StreamEvent } from '@/types'

beforeEach(() => {
  localStorage.clear()
  window.matchMedia = vi.fn((q: string) => ({
    matches: q.includes('min-width'),
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver
})

describe('K3 Z08+Z07 — Stream-Frames (Dauer/stdout)', () => {
  it('tool_done mit duration_ms → upsertToolCall erhaelt durationMs', () => {
    const store = { upsertToolCall: vi.fn() }
    applyStreamEvent(
      { type: 'tool_done', tool: 'run_shell', result: 'ok', duration_ms: 1.2 } as StreamEvent,
      store as never,
    )
    const arg = (store.upsertToolCall.mock.calls[0] as unknown[])[0] as { durationMs?: number }
    expect(arg.durationMs).toBe(1.2)
  })

  it('stdout-Frame → upsertToolCall haengt data an (append)', () => {
    const store = { upsertToolCall: vi.fn() }
    applyStreamEvent(
      { type: 'stdout', tool: 'run_shell', data: 'zeile-1' } as StreamEvent,
      store as never,
    )
    const arg = (store.upsertToolCall.mock.calls[0] as unknown[])[0] as {
      name: string
      stdout: string
    }
    expect(arg.name).toBe('run_shell')
    expect(arg.stdout).toBe('zeile-1')
  })
})

// Store integration is pinned in chatStore.streaming.test.ts (real store,
// without the component mocks of this file).

describe('K3 Z08+Z07 — Stream-Zeilen-Rendering', () => {
  it('Proof-Zeile + stdout-Tail im expandierten Detail', () => {
    const msg: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: 'fertig',
      timestamp: 1,
      tool_calls: [
        {
          id: 't1',
          name: 'run_shell',
          args: { command: 'ls' },
          result: 'a\nb',
          status: 'completed',
          duration_ms: 1.2,
          stdout: 'a\nb',
        },
      ],
    }
    render(<MessageBubble message={msg} />)
    // The measurement lives in the proof line the reader opens — one number, and
    // no chip on a finished step.
    expect(screen.queryByTestId('tool-duration-chip')).toBeNull()
    fireEvent.click(screen.getByTestId('tool-stream-row-shell').querySelector('button')!)
    // This suite's i18n mock returns keys; the proof row is the contract here.
    expect(screen.getByTestId('tool-row-proof').textContent).toContain('chat.proof')
    expect(screen.getByTestId('tool-stdout-tail').textContent).toMatch(/zeile|a/)
  })
})

describe('K3 Z09 — Swarm-Nest im Aktivitaeten-Feed', () => {
  it('Agent-Zeile mit indentierter Kind-Zeile (detail)', () => {
    render(
      <ActivityFeed
        activities={[
          {
            id: 'x1',
            label: 'Agent a1',
            status: 'running',
            detail: 'Unteraufgabe: Suche',
          } as never,
        ]}
      />,
    )
    expect(screen.getByTestId('activity-x1').textContent).toMatch(/Agent a1/)
    expect(screen.getByTestId('activity-detail-x1').textContent).toMatch(/Unteraufgabe/)
  })
})

describe('K3 Z14 — Quellen-Leiste', () => {
  it('extractSourceUrls findet nummerierte URLs, Kappung bei 6', () => {
    const urls = extractSourceUrls(
      '1. Alpha — https://alpha.example/a\n2. Beta — https://beta.example/b\n3. Gamma — https://gamma.example/c\n4. D — https://d.example\n5. E — https://e.example\n6. F — https://f.example\n7. G — https://g.example',
    )
    expect(urls.length).toBe(6)
    expect(urls[0]).toBe('https://alpha.example/a')
  })

  it('Quellen-Chips unter der Antwort, Klick oeffnet im Panel', () => {
    const seen: unknown[] = []
    const onOpen = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener('ephe:preview-open', onOpen)
    const msg: ChatMessage = {
      id: 'a1',
      role: 'assistant',
      content: 'antwort',
      timestamp: 1,
      tool_calls: [
        {
          id: 't1',
          name: 'web_search',
          args: { query: 'alpha' },
          result: '1. Alpha — https://alpha.example/a\n2. Beta — https://beta.example/b',
          status: 'completed',
        },
      ],
    }
    render(<MessageBubble message={msg} />)
    const bar = screen.getByTestId('sources-bar')
    expect(bar.children.length).toBe(2)
    fireEvent.click(screen.getByTestId('source-chip-0'))
    window.removeEventListener('ephe:preview-open', onOpen)
    expect((seen[0] as { url: string }).url).toBe('https://alpha.example/a')
  })
})

describe('K3 Z24 — Modell-Chip mit Dropdown', () => {
  it('Chip zeigt aktives Modell; Klick oeffnet Provider-Menue, Wahl setzt Provider', async () => {
    render(<ChatInput onSend={() => {}} />)
    await vi.waitFor(() =>
      expect(screen.getByTestId('model-chip').textContent).toMatch(/qwen3\.8-flash-next/),
    )
    fireEvent.click(screen.getByTestId('model-chip'))
    expect(screen.getByTestId('model-chip-menu')).toBeTruthy()
    fireEvent.click(screen.getByTestId('model-chip-option-openai_compatible'))
    await vi.waitFor(() => expect(apiMocks.setModelProvider).toBeCalled())
    const [id] = apiMocks.setModelProvider.mock.calls[0] as unknown[] as [string]
    expect(id).toBe('openai_compatible')
  })
})

describe('K3 Z29 — Terminal-Recall ↑/↓', () => {
  it('Pfeiltasten walked den Befehlsverlauf, Zaehler sichtbar', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['terminal']))
    render(<AgentPanel />)
    act(() => {
      window.dispatchEvent(new CustomEvent('ephe:preview-open', { detail: { tab: 'terminal' } }))
    })
    // P1-5: Live PTY is the default; recall/prompt live in the history mode.
    await screen.findByTestId('live-terminal')
    fireEvent.click(screen.getByTestId('terminal-mode-history'))
    const input = await screen.findByTestId('terminal-prompt-input')
    fireEvent.change(input, { target: { value: 'ls' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    // W17 P1-1: the terminal path prefers the PTY channel (runShellPty).
    await vi.waitFor(() => expect(apiMocks.runShellPty).toBeCalled())
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect((input as HTMLInputElement).value).toBe('ls')
    expect(screen.getByTestId('terminal-recall-counter').textContent).toMatch(/1\/1/)
  })
})

describe('K3 Z35 — Sidebar-Volltextsuche', () => {
  it('Inhalt-Treffer unter dem Filterfeld, Klick waehlt die Session', async () => {
    render(
      <Sidebar
        isOpen
        onClose={() => {}}
        onOpenSettings={() => {}}
        collapsed={false}
        onToggleCollapsed={() => {}}
      />,
    )
    fireEvent.change(screen.getByPlaceholderText('sidebar.searchPlaceholder'), {
      target: { value: 'alpha' },
    })
    const hit = await screen.findByTestId('sidebar-content-hit-0')
    expect(hit.textContent).toMatch(/Alpha/)
    fireEvent.click(hit)
    expect(storeState.setActiveSession).toBeCalledWith('s1')
  })
})
