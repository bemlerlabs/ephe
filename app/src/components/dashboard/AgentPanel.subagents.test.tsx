import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ChatMessage } from '@/types'

// Round-G4 (2026-09-07, reference parity): the subagents tab lists the
// swarm/agent runs of the current conversation — "Running" live, "Ended"
// with a timestamp and an expandable excerpt (subtask/summary from the activities).

vi.mock('@/lib/api', () => ({
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
  // P4-D: detail adapter — the registry record in the REST shape
  getSubagent: vi.fn(async (agentId: string) => ({
    agent_id: agentId,
    role: 'scout',
    description: 'Research HTTP timeouts',
    task: 'Find timeouts',
    model: 'm1',
    status: 'ok',
    started_ts: 1000,
    finished_ts: 1007,
    duration_ms: 7234,
    report: 'Bericht: Timeout bei 30s.',
    tool_calls: [{ tool: 'web_search', args_preview: '{"query":"http"}', ms: 850 }],
    transcript: [],
  })),
  listSubagents: vi.fn(async () => ({ agents: [] })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const MESSAGES: ChatMessage[] = [
  {
    id: 'm1',
    role: 'assistant',
    content: 'Swarm läuft',
    timestamp: Date.now() - 5 * 60_000,
    activities: [
      {
        id: 'a1',
        label: 'Agent researcher',
        status: 'running',
        detail: 'Sammelt Quellen zu Thema X',
      },
      {
        id: 'a2',
        label: 'Agent writer',
        status: 'done',
        detail: 'Zusammenfassung fertig: 3 Absaetze…',
      },
      { id: 'a3', label: 'Agent critic', status: 'failed', detail: 'Timeout nach 30s' },
      {
        id: 'a4',
        label: 'SubAgent subagent-1 (scout)',
        status: 'done',
        detail: 'Research HTTP timeouts',
      },
    ],
  },
]

function openSubagentsPane() {
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'subagents' } }))
}

describe('Subagenten-Tab (Runden-G4, Referenz-Paritaet)', () => {
  beforeEach(() => {
    localStorage.clear()
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

  const renderPane = () => {
    render(<AgentPanel messages={MESSAGES} />)
    openSubagentsPane()
  }

  it('neuer Tab ist Teil des +-Angebots und oeffnet als Pille', async () => {
    renderPane()
    const pill = (await screen.findByRole('tab', {
      name: 'agentPanel.tabSubagents',
    })) as HTMLElement
    expect(pill.getAttribute('aria-selected')).toBe('true')
  })

  it('teilt in Laufend und Abgeschlossen; Laufend-Section listet den Live-Agenten', async () => {
    renderPane()
    expect(await screen.findByTestId('subagents-running-section')).toBeTruthy()
    const running = screen.getByTestId('subagents-running-section')
    expect(within(running).getByText(/Agent researcher/)).toBeTruthy()
    expect(within(running).getByText('agentPanel.subagentRunning')).toBeTruthy()
    expect(screen.getByTestId('subagents-ended-section')).toBeTruthy()
  })

  it('Abgeschlossen-Section zeigt Status-Text und Zeitstempel, Failed rot markiert', async () => {
    renderPane()
    const ended = await screen.findByTestId('subagents-ended-section')
    expect(within(ended).getByText(/Agent writer/)).toBeTruthy()
    expect(within(ended).getByText(/Agent writer/)).toBeTruthy()
    expect(within(ended).getByText(/Agent critic/)).toBeTruthy()
    expect(within(ended).getAllByText('agentPanel.subagentFailed').length).toBeGreaterThan(0)
    // timestamp for the finished agent (relTime format 'Nm ago')
    // the test i18n mock does not interpolate — the timestamp shows up as a
    // raw key carrying the countdown placeholder.
    expect(within(ended).getAllByText(/minAgo/).length).toBeGreaterThan(0)
  })

  it('Klick auf eine abgeschlossene Zeile klappt das Excerpt auf (summary)', async () => {
    renderPane()
    const ended = await screen.findByTestId('subagents-ended-section')
    fireEvent.click(within(ended).getByTestId('subagent-row-a2'))
    expect(await within(ended).findByText('Zusammenfassung fertig: 3 Absaetze…')).toBeTruthy()
  })

  it('P4-D: Klick auf SubAgent-Zeile klappt REST-Detail auf (Steps · Worked · Report)', async () => {
    renderPane()
    const ended = await screen.findByTestId('subagents-ended-section')
    fireEvent.click(within(ended).getByTestId('subagent-row-a4'))
    // the report block only shows up once the fetch has resolved:
    await within(ended).findByTestId('subagent-report-subagent-1')
    const panel = within(ended).getByTestId('subagent-expanded-subagent-1')
    const txt = panel.textContent ?? ''
    expect(txt).toContain('web_search')
    expect(txt).toContain('850ms')
    expect(txt).toContain('agentPanel.subagentWorked')
    expect(txt).toContain('Bericht: Timeout bei 30s.')
    // clicking again collapses the row
    fireEvent.click(within(ended).getByTestId('subagent-row-a4'))
    expect(within(ended).queryByTestId('subagent-expanded-subagent-1')).toBeNull()
  })

  it('ohne Agent-Aktivität: sauberer Leerzustand', async () => {
    render(
      <AgentPanel
        messages={[{ id: 'm0', role: 'assistant', content: 'Hi', timestamp: Date.now() }]}
      />,
    )
    openSubagentsPane()
    expect(await screen.findByTestId('subagents-empty')).toBeTruthy()
  })
})
