/**
 * docs/AGENT_PANEL_CONDUCT_2026-10-11.md §3 — the closed list of what may never
 * move the pane, and §2's controls (a click that opens, the key that closes). Each
 * test names the row of that table it holds, so a re-grown auto-open fails with the
 * rule it broke rather than with a missing element.
 *
 * The streamed turn through `chat/model.ts` is proven against the built bundle in
 * `app/tests/playwright/panel-conduct.spec.ts`: that path is the shipping code end
 * to end, and a unit test would only re-mock its way to a weaker claim.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT, PANEL_STATE_EVENT } from '@/lib/panelEvents'
import { applyStreamEvent } from '@/lib/streamActions'
import { useArtifactNotice } from '@/components/dashboard/chat/useArtifactNotice'
import MessageFileCard, { producedFiles } from '@/components/dashboard/artifacts/messageCard'
import type { ChatMessage, Session } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...real,
    LAN_TOKEN: null,
    proxyFetch: vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' })),
    runShell: vi.fn(async () => ({ output: '' })),
    getTasks: vi.fn(async () => []),
    getSettings: vi.fn(async () => ({ workspace_dir: null })),
    listFs: vi.fn(async () => ({ entries: [] })),
    getAudit: vi.fn(async () => ({ entries: [] })),
    gitStatus: vi.fn(async () => ({ workspace: 'proj', git: false, branch: '', changes: [] })),
    gitDiff: vi.fn(async () => ({ path: '', diff: '', binary: false })),
    listArtifacts: vi.fn(async () => ({ artifacts: [], total: 0 })),
  }
})

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

vi.mock('./agent/LiveTerminal', () => ({ default: () => <div data-testid="live-terminal" /> }))

const openEvents: CustomEvent[] = []
function catchOpen() {
  const on = (e: Event) => openEvents.push(e as CustomEvent)
  window.addEventListener(PREVIEW_OPEN_EVENT, on)
  return () => window.removeEventListener(PREVIEW_OPEN_EVENT, on)
}

/** false→true of the pane's own broadcast. A broadcast is not a move — the pane
 *  re-broadcasts whenever a tab or the width changes while it stays open. */
function countPaneMoves(): () => number {
  let was = false
  let moves = 0
  const on = (e: Event) => {
    const open = Boolean((e as CustomEvent).detail?.open)
    if (open && !was) moves += 1
    was = open
  }
  window.addEventListener(PANEL_STATE_EVENT, on)
  return () => {
    window.removeEventListener(PANEL_STATE_EVENT, on)
    return moves
  }
}

function mockStore() {
  return {
    startTurn: vi.fn(),
    appendChunk: vi.fn(),
    appendThinking: vi.fn(),
    replaceText: vi.fn(),
    upsertToolCall: vi.fn(),
    upsertActivity: vi.fn(),
    setTurnId: vi.fn(),
    attachArtifact: vi.fn(),
    resolveSandbox: vi.fn(),
    markStreamError: vi.fn(),
    markLastUsage: vi.fn(),
    setReflecting: vi.fn(),
    setRevising: vi.fn(),
    setQualityCheck: vi.fn(),
    finishTurn: vi.fn(),
    beginHelperChat: vi.fn(),
    stepHelperChat: vi.fn(),
    endHelperChat: vi.fn(),
  } as unknown as Parameters<typeof applyStreamEvent>[1]
}

// The header toggle's own event — chat/index.tsx:431 fires exactly this on click.
const togglePane = () =>
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))

function renderPane() {
  return render(
    <MemoryRouter>
      <AgentPanel />
    </MemoryRouter>,
  )
}

const pane = () => screen.queryByRole('tabpanel')

function sessionWith(messages: ChatMessage[]): Session {
  return { id: 's1', title: 't', createdAt: Date.now(), messages }
}

const pdfToolMessage = (over: Partial<ChatMessage> = {}): ChatMessage => ({
  id: 'a1',
  role: 'assistant',
  content: 'Built.',
  timestamp: Date.now(),
  tool_calls: [
    {
      id: 't1',
      name: 'write_file',
      args: { path: '/workspace/report.pdf' },
      result: 'ok',
      status: 'completed',
    },
  ],
  ...over,
})

const pdfActivityResult: ChatMessage = {
  ...pdfToolMessage(),
  tool_calls: [],
  activities: [
    {
      id: 'a9',
      label: 'PDF: report.pdf',
      status: 'done',
      path: '/tmp/ephe/report.pdf',
      fileType: 'pdf',
      artifactId: 'art1',
    },
  ],
}

beforeEach(() => {
  localStorage.clear()
  document.body.innerHTML = ''
  openEvents.length = 0
  vi.spyOn(document, 'hasFocus').mockReturnValue(true)
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

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('conduct §3.1 — a file_result never moves the pane', () => {
  it('reduces pdf, html and image events without a single open', () => {
    const stop = catchOpen()
    const moves = countPaneMoves()
    renderPane()
    const store = mockStore()
    applyStreamEvent({ type: 'turn', turn_id: 'turn-1' } as never, store)
    for (const [type, path] of [
      ['pdf', '/tmp/ephe/report.pdf'],
      ['html', '/tmp/ephe/page.html'],
      ['png', '/tmp/ephe/chart.png'],
    ] as const) {
      applyStreamEvent(
        { type: 'file_result', file_type: type, path, id: `art-${type}` } as never,
        store,
      )
    }
    applyStreamEvent({ type: 'done' } as never, store)
    expect(openEvents).toHaveLength(0)
    expect(pane()).toBeNull()
    expect(moves()).toBe(0)
    stop()
  })
})

describe('conduct §3.2/3.3 — a finished tool artifact and a detector artifact stay put', () => {
  it('the notice hook says nothing while this window has the focus', () => {
    const stop = catchOpen()
    const { rerender } = renderHook((s) => useArtifactNotice(s), {
      initialProps: sessionWith([]),
    })
    rerender(sessionWith([pdfToolMessage()]))
    rerender(sessionWith([pdfToolMessage({ content: 'the turn is still streaming' })]))
    expect(openEvents).toHaveLength(0)
    stop()
  })

  it('the background notice is a toast with a way in, not a pane that moves', async () => {
    const { toastBus } = await import('@/lib/toast')
    const info = vi.spyOn(toastBus, 'info').mockImplementation(() => {})
    vi.mocked(document.hasFocus).mockReturnValue(false)
    const stop = catchOpen()
    const { rerender } = renderHook((s) => useArtifactNotice(s), {
      initialProps: sessionWith([]),
    })
    rerender(sessionWith([pdfToolMessage()]))
    expect(openEvents).toHaveLength(0)
    expect(info).toHaveBeenCalledTimes(1)
    // The toast's own action is the click that earns the pane.
    const action = vi.mocked(info).mock.calls[0]![2] as { onClick: () => void }
    action.onClick()
    expect(openEvents).toHaveLength(1)
    stop()
  })

  it('a session switch primes the history without announcing or opening', () => {
    const stop = catchOpen()
    const { rerender } = renderHook((s) => useArtifactNotice(s), {
      initialProps: sessionWith([]),
    })
    rerender({ ...sessionWith([pdfToolMessage()]), id: 's2' })
    expect(openEvents).toHaveLength(0)
    stop()
  })

  it('a content-less detector artifact on the message opens nothing either', () => {
    const stop = catchOpen()
    const { rerender } = renderHook((s) => useArtifactNotice(s), {
      initialProps: sessionWith([]),
    })
    rerender(
      sessionWith([
        pdfToolMessage({
          tool_calls: [],
          artifacts: [
            {
              id: 'k1',
              artifact_type: 'file_pdf',
              content: '',
              language: 'text',
              title: 'plan.pdf',
              filename: '/tmp/ephe/plan.pdf',
            },
          ],
        }),
      ]),
    )
    expect(openEvents).toHaveLength(0)
    stop()
  })
})

describe('conduct §2 — the clicks that do move it', () => {
  it('the header toggle opens the pane and closes it again', async () => {
    renderPane()
    expect(pane()).toBeNull()
    await act(async () => togglePane())
    await waitFor(() => expect(pane()).not.toBeNull())
    await act(async () => togglePane())
    await waitFor(() => expect(pane()).toBeNull())
  })

  it('a click on the message file card opens the pane on that file', async () => {
    const stop = catchOpen()
    renderPane()
    const [produced] = producedFiles(pdfActivityResult)
    render(<MessageFileCard file={produced!} />)
    expect(pane()).toBeNull()
    fireEvent.click(screen.getByTestId('message-file-open-act-a9'))
    expect(openEvents).toHaveLength(1)
    await waitFor(() => expect(pane()).not.toBeNull())
    expect(String((openEvents[0]!.detail as { url?: string }).url)).toContain('/api/artifacts/')
    stop()
  })

  it('Escape closes the pane, and a modal above it keeps the key', async () => {
    renderPane()
    await act(async () => togglePane())
    await waitFor(() => expect(pane()).not.toBeNull())
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    dialog.setAttribute('aria-modal', 'true')
    document.body.appendChild(dialog)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(pane()).not.toBeNull()
    dialog.remove()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(pane()).toBeNull())
  })
})
