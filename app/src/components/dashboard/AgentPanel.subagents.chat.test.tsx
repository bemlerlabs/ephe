import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { useChatStore } from '@/store/chatStore'
import { HELPER_PREFIX } from '@/lib/helperSession'
import type { ChatMessage } from '@/types'

// Visibility wave: a helper line is the entrance to its own chat.
// Both the live line from the conversation and the history line from the ledger
// open the same session — and via parentId the parent task stays the way back.

const HELPER_SESSION_ID = `${HELPER_PREFIX}9e8d7c6b`

const record = (overrides: Record<string, unknown> = {}) => ({
  agent_id: 'subagent-1',
  role: 'scout',
  description: 'Research HTTP timeouts',
  task: 'Finde die Timeout-Werte',
  model: 'm1',
  status: 'ok',
  started_ts: (Date.now() - 7_000) / 1000,
  finished_ts: Date.now() / 1000,
  duration_ms: 7_234,
  report: 'Bericht: 30 Sekunden.',
  tool_calls: [{ tool: 'web_search', args_preview: '{"query":"http"}', ms: 850 }],
  transcript: [],
  chat_session_id: HELPER_SESSION_ID,
  parent_session: '',
  ...overrides,
})

const apiMock = vi.hoisted(() => ({
  runShell: vi.fn(async () => ({ output: '' })),
  getTasks: vi.fn(async () => []),
  createTask: vi.fn(async () => ({ success: true })),
  updateTask: vi.fn(async () => ({ success: true })),
  deleteTask: vi.fn(async () => ({ success: true })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  listFs: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
  gitStatus: vi.fn(async () => ({ workspace: 'proj', git: false, branch: '', changes: [] })),
  gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
  getSubagent: vi.fn(async (agentId: string) => record({ agent_id: agentId })),
  listSubagents: vi.fn(async () => ({ agents: [], nextCursor: null })),
}))

vi.mock('@/lib/api', () => apiMock)

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const MESSAGES: ChatMessage[] = [
  {
    id: 'm1',
    role: 'assistant',
    content: 'Ich delegiere das.',
    timestamp: Date.now(),
    activities: [
      {
        id: 'a4',
        label: 'SubAgent subagent-1 (scout)',
        status: 'done',
        detail: 'Research HTTP timeouts',
      },
      {
        id: 'a5',
        label: 'SubAgent unknown-9 (scout)',
        status: 'done',
        detail: 'Nur als Aktivitaet bekannt',
      },
    ],
  },
]

function resetStore() {
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    checkpoints: {},
  })
  useChatStore.getState().createSession('Mutteraufgabe')
}

async function openPane() {
  render(<AgentPanel messages={MESSAGES} />)
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'subagents' } }))
  return screen.findByTestId('subagents-view')
}

/**
 * Find and click synchronously: the line rebuilds while the ledger follow-up
 * runs — an `await` in between throws the node out of the document.
 */
function clickOpenChat(agentId: string) {
  fireEvent.click(screen.getByTestId(`subagent-open-chat-${agentId}`))
}

describe('Helfer-Zeile öffnet ihren eigenen Chat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getSubagent.mockImplementation(
      async (agentId: string) => record({ agent_id: agentId }) as never,
    )
    apiMock.listSubagents.mockResolvedValue({ agents: [], nextCursor: null } as never)
    localStorage.clear()
    resetStore()
    if (!window.matchMedia) {
      window.matchMedia = vi.fn(() => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      })) as unknown as typeof window.matchMedia
    }
    if (!globalThis.ResizeObserver) {
      globalThis.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
      } as unknown as typeof globalThis.ResizeObserver
    }
  })

  it('Live-Zeile: „Chat öffnen“ aktiviert die Helfersitzung am Elternast', async () => {
    const parentId = useChatStore.getState().activeSessionId
    await openPane()
    clickOpenChat('subagent-1')

    // the link builds the session from the ledger — that is an await, not sync
    await vi.waitFor(() => expect(useChatStore.getState().activeSessionId).toBe(HELPER_SESSION_ID))
    const h = useChatStore.getState().sessions.find((s) => s.id === HELPER_SESSION_ID)
    expect(h).toBeTruthy()
    expect(h!.parentId).toBe(parentId)
    expect(h!.messages[0]!.content).toBe('Finde die Timeout-Werte')
    expect(h!.messages[h!.messages.length - 1]!.content).toBe('Bericht: 30 Sekunden.')
  })

  it('Historienzeile: ohne lokalen Chat baut ihn derselbe Ledger-Record', async () => {
    apiMock.listSubagents.mockResolvedValue({
      agents: [
        {
          agent_id: 'subagent-77',
          role: 'scout',
          description: 'Alte Delegation',
          task: 'Finde etwas Langes',
          status: 'ok',
          started_ts: (Date.now() - 60_000) / 1000,
          duration_ms: 4_000,
          tool_count: 1,
          chat_session_id: `${HELPER_PREFIX}feedface`,
          parent_session: '',
        },
      ],
      nextCursor: null,
    } as never)
    apiMock.getSubagent.mockImplementation(
      async () =>
        record({
          agent_id: 'subagent-77',
          chat_session_id: `${HELPER_PREFIX}feedface`,
          description: 'Alte Delegation',
          task: 'Finde etwas Langes',
        }) as never,
    )
    await openPane()
    const row = await screen.findByTestId('subagent-directory-row-subagent-77')
    clickOpenChat('subagent-77')
    expect(row).toBeTruthy()

    await vi.waitFor(() =>
      expect(useChatStore.getState().activeSessionId).toBe(`${HELPER_PREFIX}feedface`),
    )
    expect(apiMock.getSubagent).toHaveBeenCalledWith('subagent-77')
    expect(
      useChatStore.getState().sessions.find((s) => s.id === `${HELPER_PREFIX}feedface`)!.title,
    ).toBe('Alte Delegation')
  })

  it('bereits vorhandene Helfersitzung wird nicht doppelt angelegt', async () => {
    const parentId = useChatStore.getState().activeSessionId
    useChatStore.getState().beginHelperChat({
      chatSessionId: HELPER_SESSION_ID,
      agentId: 'subagent-1',
      role: 'scout',
      task: 'Finde die Timeout-Werte',
      description: 'Research HTTP timeouts',
      parentSession: parentId!,
    })
    await openPane()
    clickOpenChat('subagent-1')

    await vi.waitFor(() => expect(useChatStore.getState().activeSessionId).toBe(HELPER_SESSION_ID))
    const all = useChatStore.getState().sessions.filter((s) => s.id === HELPER_SESSION_ID)
    expect(all).toHaveLength(1)
    // the stream died before the done event: the ledger is the authority and
    // closes the open bubble — no endless spinner inside the helper chat
    const h = all[0]!
    expect(h.messages[1]!.streaming).toBe(false)
    expect(h.messages[1]!.content).toBe('Bericht: 30 Sekunden.')
    expect(h.parentId).toBe(parentId)
  })

  it('fehlender Ledger-Record führt ins Nichts, nicht in eine leere Hülle', async () => {
    const parentId = useChatStore.getState().activeSessionId
    apiMock.getSubagent.mockRejectedValue(new Error('404') as never)
    await openPane()
    clickOpenChat('unknown-9')
    await new Promise((r) => setTimeout(r, 10))

    expect(useChatStore.getState().activeSessionId).toBe(parentId)
    expect(useChatStore.getState().sessions.some((s) => s.id.startsWith(HELPER_PREFIX))).toBe(false)
  })
})
