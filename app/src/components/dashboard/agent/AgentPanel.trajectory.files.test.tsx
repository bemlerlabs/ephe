/**
 * A3 backwards — the assignment knows its files.
 *
 * The replay tab shows not only what a turn did, but what it left behind. Counting
 * is done by the workbench (by root_id, not by rows), and the link asks the same
 * scope question the page itself answers: /artifacts?turn=<id>.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { TrajectoryTab } from './tabsA'
import { useChatStore } from '@/store/chatStore'
import { listArtifacts } from '@/lib/api'
import type { ArtifactEntry } from '@/lib/api'

const card = (id: string, root: string, turnId?: string): ArtifactEntry => ({
  id,
  root_id: root,
  version: 1,
  session_id: 's1',
  name: `${id}.pdf`,
  path: `/werkbank/s1/${id}.pdf`,
  kind: 'pdf',
  size: 10,
  topic: 'Prüfgang',
  created_at: '2026-10-06T00:00:00+00:00',
  favorite: false,
  tags: [],
  ...(turnId ? { turn_id: turnId } : {}),
})

function WorkbankSonde() {
  const loc = useLocation()
  return <div data-testid="werkbank-mit-scope" data-search={loc.search} />
}

vi.mock('@/lib/api', () => ({
  getTrajectory: vi.fn(async () => ({
    turns: ['turn-a', 'turn-b'].map((turnId, i) => ({
      sid: 's1',
      turn_id: turnId,
      model: 'm',
      ts: 1761806357 + i * 100,
      duration_ms: 100,
      steps: [{ n: 1, type: 'done', title: 'fertig', ms: 10, state: 'ok' }],
    })),
  })),
  getSubagent: vi.fn(async () => null),
  listMemory: vi.fn(async () => ({ entries: [] })),
  searchMemory: vi.fn(async () => ({ results: [] })),
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
  listArtifacts: vi.fn(async () => ({ artifacts: [], total: 0 })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  // The number has to be visible in the test, otherwise everything checks only the key.
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) =>
      opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key,
    i18n: { language: 'en' },
  }),
}))

// jsdom gives height 0 — the virtualizer needs a measured scroll height.
const patchHeight = (prop: 'offsetHeight' | 'clientHeight') => {
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    get() {
      return this.classList.contains('overflow-y-auto') ? 600 : 0
    },
  })
}

const renderTab = () =>
  render(
    <MemoryRouter initialEntries={['/chat']}>
      <Routes>
        <Route path="/chat" element={<TrajectoryTab />} />
        <Route path="/artifacts" element={<WorkbankSonde />} />
      </Routes>
    </MemoryRouter>,
  )

describe('Dateien am Turn-Kopf (R4 A3 rückwärts)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    patchHeight('offsetHeight')
    patchHeight('clientHeight')
    vi.mocked(listArtifacts).mockClear()
    vi.mocked(listArtifacts).mockResolvedValue({ artifacts: [], total: 0 })
  })

  it('fragt die Werkbank nach der Session, nicht nach der Timeline', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    expect(listArtifacts).toHaveBeenCalledWith(expect.objectContaining({ session_id: 's1' }))
  })

  it('zählt Aufträge nach Datei, nicht nach Version, und ignoriert Karten ohne Turn', async () => {
    vi.mocked(listArtifacts).mockResolvedValue({
      artifacts: [
        card('v1', 'root-1', 'turn-a'),
        card('v2', 'root-1', 'turn-a'), // same file, new version
        card('v3', 'root-2', 'turn-a'),
        card('v4', 'root-3', 'turn-b'),
        card('alt', 'root-9'), // predates the chain: belongs to no assignment
      ],
      total: 5,
    })
    renderTab()
    expect((await screen.findByTestId('trajectory-turn-files-0')).textContent).toContain(
      'agentPanel.turnFiles:2',
    )
    expect(screen.getByTestId('trajectory-turn-files-1').textContent).toContain(
      'agentPanel.turnFiles:1',
    )
  })

  it('ohne Dateien bleibt der Kopf leer statt eine Null zu zeigen', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    expect(screen.queryByTestId(/trajectory-turn-files/)).not.toBeInTheDocument()
  })

  it('der Klick öffnet die Werkbank mit dem Turn als Scope', async () => {
    vi.mocked(listArtifacts).mockResolvedValue({
      artifacts: [card('v1', 'root-1', 'turn-b')],
      total: 1,
    })
    renderTab()
    fireEvent.click(await screen.findByTestId('trajectory-turn-files-1'))
    const sonde = await screen.findByTestId('werkbank-mit-scope')
    expect(sonde.getAttribute('data-search')).toBe('?turn=turn-b')
  })
})
