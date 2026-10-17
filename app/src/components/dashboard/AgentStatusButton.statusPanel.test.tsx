import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AgentStatusButton from '@/components/dashboard/AgentStatusButton'
import type { ChatMessage } from '@/types'

// P0 macro-plan wave (2026-09-28, reference "Expand status" panel):
// [F10] the turn timer ("Working for Xm Ys"), the progress checklist (Plan · n/m)
// and [F9] the query map ("Jump to query N") live inside the expandable status.

vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => []),
  getSky: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

vi.mock('@/lib/api/misc', () => ({
  gitStatus: vi.fn(async () => ({ workspace: 'proj', git: true, branch: 'main', changes: [] })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: vi.fn() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const PLAN_TEXT = '**Plan · 1/3**\n[x] Recherche\n[>] Implementierung\n[ ] Tests'

const SESSION: ChatMessage[] = [
  {
    id: 'q1',
    role: 'user',
    content: 'Erste Frage an den Agenten',
    timestamp: Date.now() - 180_000,
  },
  { id: 'a1', role: 'assistant', content: 'Erste Antwort', timestamp: Date.now() - 150_000 },
  { id: 'q2', role: 'user', content: 'Zweite Frage\nmit Details', timestamp: Date.now() - 120_000 },
  {
    id: 'a2',
    role: 'assistant',
    content: PLAN_TEXT,
    timestamp: Date.now() - 90_000,
    streaming: true,
  },
]

describe('AgentStatusButton (Status-Panel-Trio P0)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('[F10] streamender Turn ohne Subagent-Aktivität zeigt Timer und „working“-Pille', async () => {
    render(<AgentStatusButton messages={SESSION} />)
    const pill = await screen.findByTestId('agent-status-pill')
    expect(pill.textContent).toContain('agentStatus.workingFor')
    fireEvent.click(pill)
    const body = await screen.findByTestId('agent-status-body')
    expect(screen.getByTestId('agent-status-timer')).toBeTruthy()
    expect(body.textContent).toContain('agentStatus.workingFor')
  })

  it('ohne laufenden Turn gibt es keinen Timer und die Pille bleibt „bereit“', async () => {
    render(
      <AgentStatusButton
        messages={[{ id: 'm1', role: 'assistant', content: 'fertig', timestamp: Date.now() }]}
      />,
    )
    const pill = await screen.findByTestId('agent-status-pill')
    expect(pill.textContent).toContain('agentStatus.idle')
    fireEvent.click(pill)
    await screen.findByTestId('agent-status-popover')
    expect(screen.queryByTestId('agent-status-timer')).toBeNull()
  })

  it('Progress-Checkliste zeigt Plan-Stand mit done/total und Item-Status', async () => {
    render(<AgentStatusButton messages={SESSION} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const section = await screen.findByTestId('agent-status-progress')
    expect(screen.getByTestId('agent-status-progress-count').textContent).toBe('1/3')
    expect(screen.getByTestId('agent-status-progress-item-0').dataset.status).toBe('done')
    expect(screen.getByTestId('agent-status-progress-item-1').dataset.status).toBe('active')
    expect(screen.getByTestId('agent-status-progress-item-2').dataset.status).toBe('pending')
    expect(section.textContent).toContain('Implementierung')
  })

  it('[F9] Query-Map listet User-Queries; Klick feuert QUERY_JUMP_EVENT mit der Message-Id', async () => {
    render(<AgentStatusButton messages={SESSION} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const map = await screen.findByTestId('agent-status-query-map')
    expect(map.textContent).toContain('Erste Frage an den Agenten')
    // Multi-line query: only the first line becomes the label.
    expect(
      (screen.getByTestId('agent-status-jump-1').textContent ?? '').includes('mit Details'),
    ).toBe(false)

    const seen: Array<{ type: string; detail?: unknown }> = []
    const catcher = (e: Event) => seen.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('ephe:query-jump', catcher)
    try {
      fireEvent.click(screen.getByTestId('agent-status-jump-1'))
    } finally {
      window.removeEventListener('ephe:query-jump', catcher)
    }
    const ev = seen.find((x) => x.type === 'ephe:query-jump')
    expect(ev).toBeTruthy()
    expect((ev!.detail as { messageId?: string }).messageId).toBe('q2')
  })
})

// P6 B2/B3 (per-section collapse norm): per-section collapse,
// scroll policy table, goal-/environment section.
describe('AgentStatusButton Sektionen (P6 B2/B3)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('je Sektion ein eigenes Collapsible: Kollaps von plan lässt queries offen', async () => {
    render(<AgentStatusButton messages={SESSION} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    await screen.findByTestId('agent-status-body')
    expect(screen.getByTestId('status-section-head-plan').getAttribute('aria-expanded')).toBe(
      'true',
    )
    expect(screen.getByTestId('status-section-head-queries').getAttribute('aria-expanded')).toBe(
      'true',
    )
    fireEvent.click(screen.getByTestId('status-section-head-plan'))
    expect(screen.queryByTestId('status-section-body-plan')).toBeNull()
    // the other section stays open including its content
    expect(screen.getByTestId('status-section-body-queries')).toBeTruthy()
    expect(screen.getByTestId('agent-status-jump-0')).toBeTruthy()
  })

  it('Chevron-Opacity-Muster + max-h-Policy je Sektion am DOM', async () => {
    render(<AgentStatusButton messages={SESSION} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const head = await screen.findByTestId('status-section-head-plan')
    expect(head.className).toContain('pr-8')
    expect(head.querySelector('svg')?.getAttribute('class')).toContain('opacity-0')
    expect(head.querySelector('svg')?.getAttribute('class')).toContain('group-hover:opacity-100')
    const body = screen.getByTestId('status-section-body-plan')
    expect(body.className).toContain('max-h-80')
    const queriesBody = screen.getByTestId('status-section-body-queries')
    expect(queriesBody.className).toContain('max-h-48')
    // section attribute for the catalogue
    expect(document.querySelector('[data-status-section="plan"]')).toBeTruthy()
    expect(document.querySelector('[data-status-section="queries"]')).toBeTruthy()
  })

  it('goal-Sektion rendert die erste User-Query; environment zeigt Branch', async () => {
    render(<AgentStatusButton messages={SESSION} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const goal = await screen.findByTestId('agent-status-goal')
    expect(goal.textContent).toContain('Erste Frage an den Agenten')
    const env = await screen.findByTestId('agent-status-environment')
    expect(env.textContent).toContain('main')
  })

  it('ohne git (git.git=false) bleibt die environment-Sektion weg', async () => {
    const { gitStatus } = (await import('@/lib/api/misc')) as unknown as {
      gitStatus: ReturnType<typeof vi.fn>
    }
    gitStatus.mockResolvedValue({ workspace: 'proj', git: false, branch: '', changes: [] })
    render(
      <AgentStatusButton
        messages={[
          { id: 'q1', role: 'user', content: 'Nur eine Frage', timestamp: Date.now() - 60_000 },
        ]}
      />,
    )
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    expect(await screen.findByTestId('agent-status-goal')).toBeTruthy()
    await vi.waitFor(() => expect(gitStatus).toHaveBeenCalled())
    expect(screen.queryByTestId('agent-status-environment')).toBeNull()
  })
})
