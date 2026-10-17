import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AgentStatusButton from '@/components/dashboard/AgentStatusButton'
import type { ChatMessage } from '@/types'

// H-round H3 (2026-09-07, reference parity): the status readout top right like
// in the reference product — a compact pill shows live what the agent
// is working on; the click opens a popover with activity, running
// subagents and open tasks; every entry jumps into the matching
// pane tab. The pill is collapsible (only the dot while idle).

vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => [
    { id: 't1', title: 'Regression testen', status: 'pending', project: null },
    { id: 't2', title: 'Bericht schreiben', status: 'pending', project: null },
  ]),
  // S4: the ephemerides row in the status popover — offline it stays hidden.
  getSky: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

vi.mock('react-i18next', () => ({
  // initReactI18next stub: SkyStatusLine pulls the chatStore (→ src/i18n.ts)
  // into the module graph; the i18n.ts that really loads needs the export.
  initReactI18next: { type: '3rdParty', init: vi.fn() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const IDLE: ChatMessage[] = [
  { id: 'm1', role: 'assistant', content: 'fertig', timestamp: Date.now() - 60_000 },
]
const WORKING: ChatMessage[] = [
  {
    id: 'm1',
    role: 'assistant',
    content: 'arbeitet',
    timestamp: Date.now(),
    activities: [
      { id: 'a1', label: 'Agent researcher', status: 'running', detail: 'Sammelt Quellen' },
      { id: 'a2', label: 'Agent writer', status: 'done', detail: 'Fertig' },
    ],
  },
]

describe('AgentStatusButton (H3, Referenz-Paritaet)', () => {
  beforeEach(() => {
    window.localStorage.removeItem('ephe_status_collapsed')
  })

  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('Leerlauf: kompakte Pille mit Bereit-Status, keine Laufzeile', async () => {
    render(<AgentStatusButton messages={IDLE} />)
    const pill = await screen.findByTestId('agent-status-pill')
    expect(pill.textContent).toContain('agentStatus.idle')
    expect(screen.queryByTestId('agent-status-activity')).toBeNull()
  })

  it('Arbeitet-Zustand: laufende Aktivitaet sichtbar (Agent + Detail)', async () => {
    render(<AgentStatusButton messages={WORKING} />)
    const pill = await screen.findByTestId('agent-status-pill')
    expect(pill.textContent).toContain('Agent researcher')
    expect(screen.getByTestId('agent-status-activity')).toBeTruthy()
  })

  it('Popover listet laufende Subagenten und offene Aufgaben mit Zaehlern', async () => {
    render(<AgentStatusButton messages={WORKING} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const popover = await screen.findByTestId('agent-status-popover')
    expect(popover.textContent).toContain('agentStatus.subagentsSection')
    expect(popover.textContent).toContain('Sammelt Quellen')
    expect(popover.textContent).toContain('Regression testen')
    expect(screen.getByTestId('agent-status-task-count')).toBeTruthy()
  })

  it('Subagenten-Klick oeffnet den Subagenten-Tab im Pane', async () => {
    render(<AgentStatusButton messages={WORKING} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const seen: Array<{ type: string; detail?: unknown }> = []
    const catcher = (e: Event) => seen.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('ephe:preview-open', catcher)
    try {
      fireEvent.click(await screen.findByTestId('agent-status-subagent-a1'))
    } finally {
      window.removeEventListener('ephe:preview-open', catcher)
    }
    const ev = seen.find((x) => x.type === 'ephe:preview-open')
    expect(ev).toBeTruthy()
    expect((ev!.detail as { tab?: string }).tab).toBe('subagents')
  })

  it('the steps row opens the Steps page in the settings (no pane tab any more)', async () => {
    render(<AgentStatusButton messages={IDLE} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    const seen: Array<{ type: string; detail?: unknown }> = []
    const catcher = (e: Event) => seen.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('ephe:open-settings', catcher)
    const tabCatcher = (e: Event) => seen.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('ephe:settings-tab', tabCatcher)
    try {
      fireEvent.click(await screen.findByTestId('agent-status-tasks-link'))
    } finally {
      window.removeEventListener('ephe:open-settings', catcher)
      window.removeEventListener('ephe:settings-tab', tabCatcher)
    }
    // The panel tab that rendered the same steps a second time is gone: the
    // count row opens the one steps surface left, its page in the settings.
    expect(seen.map((x) => x.type)).toEqual(['ephe:open-settings', 'ephe:settings-tab'])
    expect((seen[1]!.detail as { tab?: string }).tab).toBe('tasks')
    expect(seen.some((x) => x.type === 'ephe:preview-open')).toBe(false)
  })

  it('Einklappen: Kopfzeile bleibt stehen, Inhalt verschwindet; erneut aufklappen zeigt ihn wieder', async () => {
    render(<AgentStatusButton messages={WORKING} />)
    const pill = await screen.findByTestId('agent-status-pill')
    fireEvent.click(pill)
    await screen.findByTestId('agent-status-popover')
    expect(screen.queryByTestId('agent-status-body')).toBeTruthy()

    fireEvent.click(screen.getByTestId('agent-status-collapse'))
    await waitFor(() => expect(screen.queryByTestId('agent-status-body')).toBeNull())
    // Reference-B parity: the panel stays standing as a header row with a compact summary.
    expect(screen.queryByTestId('agent-status-popover')).toBeTruthy()
    expect(screen.queryByTestId('agent-status-collapsed-summary')).toBeTruthy()

    fireEvent.click(screen.getByTestId('agent-status-collapse'))
    await waitFor(() => expect(screen.queryByTestId('agent-status-body')).toBeTruthy())
    expect(screen.queryByTestId('agent-status-collapsed-summary')).toBeNull()
  })

  it('Kollapser-Zustand wird gemurmt und ueberlebt ein Remount', async () => {
    const { unmount } = render(<AgentStatusButton messages={WORKING} />)
    const pill = await screen.findByTestId('agent-status-pill')
    fireEvent.click(pill)
    fireEvent.click(await screen.findByTestId('agent-status-collapse'))
    expect(window.localStorage.getItem('ephe_status_collapsed')).toBe('1')
    unmount()

    render(<AgentStatusButton messages={WORKING} />)
    fireEvent.click(await screen.findByTestId('agent-status-pill'))
    await screen.findByTestId('agent-status-popover')
    expect(screen.queryByTestId('agent-status-body')).toBeNull()
    expect(screen.queryByTestId('agent-status-collapsed-summary')).toBeTruthy()
  })

  it('zwei Pillen wie das Referenz-Bild: Expand-Status + Statuszeile', async () => {
    render(<AgentStatusButton messages={WORKING} />)
    expect(await screen.findByTestId('agent-status-expand')).toBeTruthy()
    expect(screen.getByTestId('agent-status-pill')).toBeTruthy()
    expect(screen.getByTestId('agent-status-expand').textContent).toContain(
      'agentStatus.expandStatus',
    )
  })

  it('S3: Popover klappt nach OBEN auf, wenn die Pille unten in der Statuszeile dockt', async () => {
    render(<AgentStatusButton messages={IDLE} />)
    const pill = await screen.findByTestId('agent-status-pill')
    pill.getBoundingClientRect = () =>
      ({
        top: window.innerHeight - 40,
        bottom: window.innerHeight - 8,
        left: 0,
        right: 200,
        width: 200,
        height: 32,
        x: 0,
        y: window.innerHeight - 40,
        toJSON: () => ({}),
      }) as DOMRect
    fireEvent.click(pill)
    const popover = await screen.findByTestId('agent-status-popover')
    // Bottom-anchored: bottom set, top empty — otherwise the panel
    // lands below the viewport and the owner sees nothing.
    expect(popover.style.bottom).not.toBe('')
    expect(popover.style.top).toBe('')
  })

  it('S3: am oberen Rand bleibt das Popover top-anchored', async () => {
    render(<AgentStatusButton messages={IDLE} />)
    const pill = await screen.findByTestId('agent-status-pill')
    pill.getBoundingClientRect = () =>
      ({
        top: 8,
        bottom: 40,
        left: 0,
        right: 200,
        width: 200,
        height: 32,
        x: 0,
        y: 8,
        toJSON: () => ({}),
      }) as DOMRect
    fireEvent.click(pill)
    const popover = await screen.findByTestId('agent-status-popover')
    expect(popover.style.top).not.toBe('')
    expect(popover.style.bottom).toBe('')
  })
})
