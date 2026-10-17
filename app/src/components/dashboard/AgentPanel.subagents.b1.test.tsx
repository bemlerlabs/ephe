import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import AgentPanel from '@/components/dashboard/AgentPanel'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ChatMessage } from '@/types'

// P6 B1 (Ephe norm, ref-02/03/10): the directory with a title header, an Ended
// header at 0, cursor pagination (a "Show more" entry only with a nextCursor), an
// error row with role=alert; the detail view with numbered steps, right-aligned
// durations and a report section; and the panel tab bar's plus menu normalized to
// exactly 4 entries.

const LIST_PAGE_1 = {
  agents: [
    {
      agent_id: 'subagent-1',
      role: 'scout',
      description: 'Research HTTP timeouts',
      task: 'Find timeouts',
      status: 'ok',
      started_ts: 1000,
      duration_ms: 7234,
      tool_count: 1,
    },
  ],
  nextCursor: 'c2',
}
const LIST_PAGE_2 = {
  agents: [
    {
      agent_id: 'subagent-2',
      role: 'writer',
      description: 'Draft summary',
      task: 'Draft',
      status: 'ok',
      started_ts: 900,
      duration_ms: 12345,
      tool_count: 0,
    },
  ],
  nextCursor: null,
}

const mocks = vi.hoisted(() => ({ list: vi.fn(), detail: vi.fn() }))

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
  getSubagent: mocks.detail,
  listSubagents: mocks.list,
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
      { id: 'a1', label: 'Agent researcher', status: 'running', detail: 'Sammelt Quellen' },
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

describe('Subagent-Directory B1 (ref-02/03/10)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
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

  it('Ended-Header erscheint bei 0 Ended-Einträgen (Running-Sektion allein)', async () => {
    // only running activity → ended.length === 0, but the header still has to stand.
    render(
      <AgentPanel
        messages={[
          {
            id: 'm1',
            role: 'assistant',
            content: 'x',
            timestamp: Date.now(),
            activities: [{ id: 'a1', label: 'Agent researcher', status: 'running' }],
          },
        ]}
      />,
    )
    openSubagentsPane()
    const ended = await screen.findByTestId('subagents-ended-section')
    expect(ended.textContent).toContain('agentPanel.subagentsEnded')
  })

  it('Detail zeigt nummerierte Steps mit rechtsbündigen Dauern + Report-Sektion', async () => {
    mocks.detail.mockResolvedValue({
      agent_id: 'subagent-1',
      role: 'scout',
      description: 'Research HTTP timeouts',
      task: 'Find timeouts',
      model: 'm1',
      status: 'ok',
      started_ts: 1000,
      finished_ts: 1007,
      duration_ms: 7234,
      report: 'Bericht: Timeout bei 30s.',
      tool_calls: [
        { tool: 'web_search', args_preview: '{"query":"http"}', ms: 850 },
        { tool: 'read_file', args_preview: '', ms: 3100 },
      ],
      transcript: [],
    })
    render(<AgentPanel messages={MESSAGES} />)
    openSubagentsPane()
    const ended = await screen.findByTestId('subagents-ended-section')
    fireEvent.click(within(ended).getByTestId('subagent-row-a4'))
    await within(ended).findByTestId('subagent-report-subagent-1')
    const panel = within(ended).getByTestId('subagent-expanded-subagent-1')
    // numbered steps 01/02 in the two-digit format
    expect(within(panel).getByTestId('subagent-step-0').textContent).toContain('01')
    expect(within(panel).getByTestId('subagent-step-1').textContent).toContain('02')
    // the duration of each step, right-aligned
    const dur0 = within(panel).getByTestId('subagent-step-duration-0')
    expect(dur0.textContent).toBe('850ms')
    expect(dur0.className).toContain('text-right')
    // the report section with its own section title
    expect(within(panel).getByText('agentPanel.subagentReport')).toBeTruthy()
    expect(panel.textContent).toContain('Bericht: Timeout bei 30s.')
  })

  it('Show more erscheint nur bei nextCursor und lädt die zweite Seite', async () => {
    mocks.list.mockResolvedValueOnce(LIST_PAGE_1).mockResolvedValueOnce(LIST_PAGE_2)
    render(<AgentPanel messages={MESSAGES} />)
    openSubagentsPane()
    const btn = await screen.findByTestId('subagents-show-more')
    expect(mocks.list).toHaveBeenCalledTimes(1)
    expect(mocks.list.mock.calls[0]![0]).toBeUndefined()
    fireEvent.click(btn)
    await vi.waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2))
    expect(mocks.list.mock.calls[1]![0]).toBe('c2')
    await screen.findByTestId('subagent-directory-row-subagent-2')
    // page 2 returns nextCursor null -> no show-more entry any longer
    expect(screen.queryByTestId('subagents-show-more')).toBeNull()
  })

  it('Fetch-Fehler zeigt eine role=alert-Zeile', async () => {
    mocks.list.mockRejectedValueOnce(new Error('boom'))
    render(<AgentPanel messages={MESSAGES} />)
    openSubagentsPane()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('agentPanel.error')
  })

  it('+-Menü listet exakt die 4 Menü-Keys in Reihenfolge', async () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    render(<AgentPanel messages={MESSAGES} />)
    openSubagentsPane()
    fireEvent.click(await screen.findByTestId('panel-add-tab'))
    const menu = screen.getByTestId('panel-add-menu')
    const items = within(menu).getAllByTestId(/panel-new-tab-item-/)
    expect(items.map((el) => el.getAttribute('data-testid'))).toEqual([
      'panel-new-tab-item-side',
      'panel-new-tab-item-review',
      'panel-new-tab-item-terminal',
      'panel-new-tab-item-browser',
    ])
  })
})
