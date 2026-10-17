/**
 * R4-A2 — the workbench is a page, no longer just a pop-up.
 *
 * What is checked is the cut the plan promises: the shelf grouped by `kind`, the
 * archive of adopted copies, the detail on the right carrying only the fields the
 * index really holds, and the expiry question between the header and the shelf.
 * The count in the header comes from /stats (over all rows), not from the list
 * slice currently shown.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const api = vi.hoisted(() => ({
  listArtifacts: vi.fn(),
  artifactStats: vi.fn(),
  artifactExportUrl: () => '/api/artifacts/export',
  artifactFileUrl: (id: string, download = false) =>
    `/api/artifacts/${id}/file${download ? '?download=1' : ''}`,
  getArtifact: vi.fn(),
  listArtifactVersions: vi.fn(),
  favoriteArtifact: vi.fn(),
  removeArtifact: vi.fn(),
  adoptArtifact: vi.fn(),
  artifactPreview: vi.fn(),
  artifactProvenance: vi.fn(),
  listArtifactExpiry: vi.fn(),
  answerArtifactExpiry: vi.fn(),
}))

vi.mock('@/lib/api', () => api)

import type { ArtifactExpiry } from '@/lib/api'
import ArtifactsPage from './ArtifactsPage'

const pdf = {
  id: 'a1',
  root_id: 'a1',
  version: 1,
  session_id: 'sess-7',
  name: 'bericht.pdf',
  path: '/home/x/.ephe/artifacts/sess-7/bericht.pdf',
  kind: 'pdf',
  size: 2048,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: [],
  origin_path: '/home/x/.ephe/artifacts/sess-7/bericht.pdf',
  adopted_path: '',
  content_hash: 'sha256:a',
  viewed_at: null,
  turn_id: 'a1b2c3d4e5f6',
  call_id: 'a1b2c3-0',
  expires_at: '2026-11-05T09:00:00+00:00',
  keep: false,
}
const adopted = {
  ...pdf,
  id: 'b2',
  root_id: 'b2',
  name: 'deck.pptx',
  kind: 'pptx',
  adopted_path: '/Users/x/Desktop/deck.pptx',
}

const render_at = (path = '/artifacts') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/artifacts" element={<ArtifactsPage />} />
        <Route path="/artifacts/:view" element={<ArtifactsPage />} />
      </Routes>
    </MemoryRouter>,
  )

beforeEach(() => {
  vi.clearAllMocks()
  api.listArtifactVersions.mockResolvedValue({ versions: [] })
  api.listArtifactExpiry.mockResolvedValue({ due: [], count: 0, bytes: 0, days: 30 })
  api.artifactPreview.mockResolvedValue({ mode: 'none', reason: 'no-text-preview' })
  api.artifactProvenance.mockResolvedValue({
    known: false,
    turn_id: '',
    call_id: '',
    args_hash: '',
    session_id: '',
    calls: [],
  })
  api.removeArtifact.mockImplementation(async (id: string) => ({
    deleted: id,
    file_removed: false,
  }))
  api.favoriteArtifact.mockImplementation(async (id: string) => ({ id, favorite: true }))
  api.listArtifacts.mockResolvedValue({ artifacts: [pdf, adopted], total: 2 })
  api.artifactStats.mockResolvedValue({
    count: 2,
    bytes: 4096,
    by_kind: [{ kind: 'pdf', count: 1, bytes: 2048 }],
    expiring_count: 1,
    expiring_bytes: 2048,
    next_expiry: '2026-11-05T09:00:00+00:00',
  })
  api.getArtifact.mockImplementation(async (id: string) => ({
    ...pdf,
    ...(id === 'b2' ? adopted : {}),
    adopted_state: id === 'b2' ? 'current' : 'none',
  }))
})

describe('ArtifactsPage', () => {
  it('zeigt das Regal mit den Arten als Gruppen', async () => {
    render_at()
    await waitFor(() => expect(screen.getByTestId('artifacts-page')).toBeTruthy())
    expect(await screen.findByText('bericht.pdf')).toBeTruthy()
    // The group heading carries the kind name from the locale file — in this test
    // the i18n mock returns the key, which is the proof that the surface no longer
    // writes German constants into an English interface.
    expect(screen.getByRole('heading', { name: /PDF/ })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /PPTX/ })).toBeTruthy()
  })

  it('zählt im Kopf über alle Zeilen, nicht über die Liste', async () => {
    render_at()
    const stats = await screen.findByTestId('artifacts-stats')
    expect(stats.textContent).toContain(
      'artifacts.page.stats {"count":2,"bytes":"4,096"}'.slice(0, 24),
    )
    expect(stats.textContent).toContain('artifacts.page.expiring')
  })

  it('öffnet die Karte rechts mit Herkunft und Frist', async () => {
    render_at()
    fireEvent.click(await screen.findByTestId('artifact-select-a1'))
    const detail = await screen.findByTestId('artifact-detail')
    // The call id belongs to a turn id — without it the card shows nothing,
    // because a bare "0" is a counter reading, not a provenance.
    expect(detail.textContent).toContain('a1b2c3-0')
    expect(detail.textContent).toContain('sess-7')
    expect(api.getArtifact).toHaveBeenCalledWith('a1')
  })

  it('filtert die Ablage auf übernommene Kopien', async () => {
    render_at('/artifacts/ablage')
    await waitFor(() => expect(screen.getByTestId('artifacts-page')).toBeTruthy())
    expect(await screen.findByText('deck.pptx')).toBeTruthy()
    expect(screen.queryByText('bericht.pdf')).toBeNull()
    // the copy keeps its own state, not a claim
    expect((await screen.findByTestId('artifact-detail')).textContent).toContain(
      'artifacts.page.adopted.current',
    )
  })

  it('sagt den Leerstand, statt ihn zu verschweigen', async () => {
    api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
    render_at()
    expect(await screen.findByTestId('artifacts-shelf-empty')).toBeTruthy()
  })

  it('meldet einen Fehler als Fehler, nicht als leere Werkbank', async () => {
    api.listArtifacts.mockRejectedValue(new Error('down'))
    render_at()
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByTestId('artifacts-shelf-empty')).toBeNull()
  })

  /**
   * R5 leftovers, finding 2: the tab read "Adopted 0" without explaining what
   * adopted means. The page subtitle says it once, globally; the tab itself does
   * not — and on the shelf a sentence about the archive would be out of place.
   */
  it('erklärt auf der Ablage, was „übernommen" bedeutet', async () => {
    render_at('/artifacts/ablage')
    const hint = await screen.findByTestId('artifacts-ablage-hint')
    expect(hint.textContent).toContain('artifacts.page.ablageHint')
  })

  it('hängt den Satz nicht ins Regal', async () => {
    render_at()
    await screen.findByText('bericht.pdf')
    expect(screen.queryByTestId('artifacts-ablage-hint')).toBeNull()
  })

  it('erklärt den Reiter auch, bevor ihn jemand anklickt', async () => {
    render_at()
    await screen.findByText('bericht.pdf')
    const reiter = screen.getByRole('link', { name: /artifacts.page.view.ablage/ })
    expect(reiter.getAttribute('title')).toContain('artifacts.page.ablageHint')
  })

  /**
   * R5 leftovers, finding 3: "PDF (30)" on the chip and "PDF 30" on the group
   * heading sat 40 px above each other. The number stays on the heading — it is
   * the only one of the two that counts exactly the rows it is written over.
   */
  it('trägt die Zahl am Gruppenkopf, nicht am Filter', async () => {
    render_at()
    const kopf = await screen.findByRole('heading', { name: /PDF 1/ })
    expect(kopf).toBeTruthy()
    const chips = await screen.findByTestId('artifacts-kind-filter')
    expect(chips.textContent).not.toMatch(/[0-9]/)
    expect(chips.textContent).toContain('PDF')
  })

  it('bietet in der Ablage nur Arten zum Filtern an, die dort wirklich liegen', async () => {
    render_at('/artifacts/ablage')
    await screen.findByText('deck.pptx')
    // one kind alone is no filter — the row stays away instead of counting 30
    expect(screen.queryByTestId('artifacts-kind-filter')).toBeNull()
  })

  /**
   * Side finding of the same report: the chip row derived its kinds from the very
   * list it filters. Choosing "PDF" therefore also removed "All" — the only way
   * out left was the browser's reload button.
   */
  it('lässt den Ausweg stehen, wenn eine Art gesetzt ist', async () => {
    render_at()
    const chips = await screen.findByTestId('artifacts-kind-filter')
    fireEvent.click(within(chips).getByRole('button', { name: 'PDF' }))
    await waitFor(() =>
      expect(api.listArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'pdf' })),
    )
    const danach = await screen.findByTestId('artifacts-kind-filter')
    expect(within(danach).getByRole('button', { name: 'artifacts.filterAll' })).toBeTruthy()
  })

  it('zählt am Kopf das, was die Ansicht wirklich zeigt', async () => {
    render_at('/artifacts/ablage')
    expect(await screen.findByRole('heading', { name: /PPTX 1/ })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: /PDF/ })).toBeNull()
  })

  it('zeigt die Frist-Frage zwischen Kopf und Regal', async () => {
    api.listArtifactExpiry.mockResolvedValue({
      due: [pdf],
      count: 1,
      bytes: 2048,
      days: 30,
    } as unknown as ArtifactExpiry)
    render_at()
    expect(await screen.findByTestId('artifact-expiry')).toBeTruthy()
  })

  it('entfernt eine Karte nur nach Rückfrage', async () => {
    render_at()
    fireEvent.click(await screen.findByTestId('artifact-select-a1'))
    fireEvent.click(await screen.findByTestId('artifact-detail-delete'))
    expect(api.removeArtifact).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('artifact-detail-delete-file'))
    await waitFor(() => expect(api.removeArtifact).toHaveBeenCalledWith('a1', true))
  })
})

describe('Scope aus der URL (R4 A3 rückwärts)', () => {
  it('gibt turn und session an den Index weiter, nicht nur an die Fläche', async () => {
    render_at('/artifacts?turn=a1b2c3d4e5f6&session=s1')
    await waitFor(() =>
      expect(api.listArtifacts).toHaveBeenCalledWith(
        expect.objectContaining({
          turn_id: 'a1b2c3d4e5f6',
          session_id: 's1',
          limit: 500,
        }),
      ),
    )
  })

  it('ohne Scope bleibt die Liste unfiltered, statt leere Filter zu schicken', async () => {
    render_at('/artifacts')
    await waitFor(() => expect(api.listArtifacts).toHaveBeenCalled())
    const calls = api.listArtifacts.mock.calls as Record<string, unknown>[][]
    const sent = calls[calls.length - 1]?.[0] as Record<string, unknown>
    expect(sent.turn_id).toBeUndefined()
    expect(sent.session_id).toBeUndefined()
  })
})

describe('Ausweg aus der Werkbank', () => {
  function renderMitAusgang(path = '/artifacts') {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/artifacts" element={<ArtifactsPage />} />
          <Route path="/artifacts/:view" element={<ArtifactsPage />} />
          <Route path="/chat" element={<div data-testid="chat-sonde" />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('führt mit einem Knopf zurück zur Aufgabe, nicht nur per Browser-Rücken', async () => {
    renderMitAusgang()
    const back = await screen.findByTestId('artifacts-back')
    expect(back.textContent).toContain('artifacts.page.back')
    fireEvent.click(back)
    expect(await screen.findByTestId('chat-sonde')).toBeInTheDocument()
  })

  it('bleibt auch auf einer Unterseite vorhanden', async () => {
    renderMitAusgang('/artifacts/ablage')
    fireEvent.click(await screen.findByTestId('artifacts-back'))
    expect(await screen.findByTestId('chat-sonde')).toBeInTheDocument()
  })
})
