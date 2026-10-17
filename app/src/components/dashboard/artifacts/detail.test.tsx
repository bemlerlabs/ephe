// R4: the detail card of a workbench row. What is checked here is the part that
// did not exist before: labels (the PUT endpoint had no reader) and the
// provenance block, which names an old card as what it is.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import ArtifactDetailPane from './detail'

/** Where the surface lands — path + query string, checkable without a route table. */
function Ort() {
  const loc = useLocation()
  return <div data-testid="ort" data-ziel={`${loc.pathname}${loc.search}`} />
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

const api = vi.hoisted(() => ({
  getArtifact: vi.fn(),
  listArtifactVersions: vi.fn(),
  artifactProvenance: vi.fn(),
  setArtifactTags: vi.fn(),
  favoriteArtifact: vi.fn(),
  removeArtifact: vi.fn(),
  adoptWithTarget: vi.fn(),
  artifactFileUrl: (id: string, download = false) =>
    `/api/artifacts/${id}/file${download ? '?download=1' : ''}`,
}))

vi.mock('@/lib/api', async (io) => {
  const real = await io<typeof import('@/lib/api')>()
  return {
    ...real,
    getArtifact: (id: string) => api.getArtifact(id),
    listArtifactVersions: () => api.listArtifactVersions(),
    artifactProvenance: (id: string) => api.artifactProvenance(id),
    setArtifactTags: (id: string, tags: string[]) => api.setArtifactTags(id, tags),
  }
})
vi.mock('./adoptFlow', () => ({ adoptWithTarget: (id: string) => api.adoptWithTarget(id) }))

const card = (over: Record<string, unknown> = {}) => ({
  id: 'a1',
  root_id: 'a1',
  version: 1,
  session_id: 's1',
  name: 'bericht.pdf',
  path: '/home/x/.ephe/artifacts/s1/bericht.pdf',
  kind: 'pdf',
  size: 2048,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: ['vorstand'],
  origin_path: '/home/x/.ephe/artifacts/s1/bericht.pdf',
  adopted_path: '',
  content_hash: 'sha256:a',
  viewed_at: null,
  turn_id: 'a1b2c3d4e5f6',
  call_id: 'a1b2c3-0',
  expires_at: '2026-11-05T09:00:00+00:00',
  keep: false,
  adopted_state: 'none',
  ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  api.getArtifact.mockResolvedValue(card())
  api.listArtifactVersions.mockResolvedValue({ versions: [] })
  api.artifactProvenance.mockResolvedValue({
    known: true,
    turn_id: 'a1b2c3d4e5f6',
    call_id: 'a1b2c3-0',
    args_hash: '',
    session_id: 's1',
    calls: [{ tool: 'create_pdf', args: 'title=Bericht', status: 'ok', duration_ms: 900 }],
  })
  api.setArtifactTags.mockResolvedValue({ id: 'a1', tags: [] })
})
afterEach(cleanup)

// The card header carries the decision, not the detour: the page promises that the
// user chooses what lands on their disk — so the emphasis belongs to the adopt
// button. A grey, disabled button must not hold it, which is why the emphasis
// moves once the copy is already current.
describe('Betonung der Gesten', () => {
  const zeige = async (ueber: Record<string, unknown>) => {
    api.getArtifact.mockResolvedValue(card(ueber))
    const ergebnis = render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    await screen.findByTestId('artifact-detail-adopt')
    return ergebnis
  }
  const klasse = (el: HTMLElement | null) => el?.getAttribute('class') ?? ''

  it('betont Übernehmen, solange nichts auf der Platte liegt', async () => {
    const { container } = await zeige({ adopted_state: 'none' })
    expect(klasse(container.querySelector('[data-testid="artifact-detail-adopt"]'))).toContain(
      'bg-brand/20',
    )
    expect(
      klasse(container.querySelector('[data-testid="artifact-detail-download"]')),
    ).not.toContain('bg-brand/20')
  })

  it('gibt die Betonung dem Herunterladen, wenn Übernehmen deaktiviert ist', async () => {
    const { container } = await zeige({
      adopted_state: 'current',
      adopted_path: '/Users/x/Berichte/bericht.pdf',
    })
    const adopt = container.querySelector(
      '[data-testid="artifact-detail-adopt"]',
    ) as HTMLButtonElement
    expect(adopt.disabled).toBe(true)
    expect(klasse(adopt)).not.toContain('bg-brand/20')
    expect(klasse(container.querySelector('[data-testid="artifact-detail-download"]'))).toContain(
      'bg-brand/20',
    )
  })
})

describe('ArtifactDetailPane', () => {
  it('zeigt die Etiketten der Karte', async () => {
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    const box = await screen.findByTestId('artifact-tags')
    expect(box.textContent).toContain('vorstand')
  })

  it('schreibt ein neues Etikett über den PUT-Endpunkt', async () => {
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    const input = await screen.findByLabelText('artifacts.page.tagAdd')
    fireEvent.change(input, { target: { value: 'q3' } })
    fireEvent.click(screen.getByTestId('artifact-tag-add'))
    await waitFor(() => expect(api.setArtifactTags).toHaveBeenCalledWith('a1', ['vorstand', 'q3']))
  })

  it('fügt dasselbe Etikett nicht zweimal ein', async () => {
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    const input = await screen.findByLabelText('artifacts.page.tagAdd')
    fireEvent.change(input, { target: { value: 'vorstand' } })
    fireEvent.click(screen.getByTestId('artifact-tag-add'))
    await new Promise((r) => setTimeout(r, 20))
    expect(api.setArtifactTags).not.toHaveBeenCalled()
  })

  it('entfernt ein Etikett durch die Liste ohne es', async () => {
    api.getArtifact.mockResolvedValue(card({ tags: ['vorstand', 'q3'] }))
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByLabelText('artifacts.page.tagRemove: q3'))
    await waitFor(() => expect(api.setArtifactTags).toHaveBeenCalledWith('a1', ['vorstand']))
  })

  it('zeigt die Kette: Turn, Ruf und der Werkzeugruf dahinter', async () => {
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    const prov = await screen.findByTestId('artifact-provenance')
    expect(prov.textContent).toContain('a1b2c3d4e5f6')
    expect(prov.textContent).toContain('create_pdf')
    expect(prov.textContent).toContain('900 ms')
  })

  it('führt von der Karte zurück zu ihrem Auftrag', async () => {
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
        <Ort />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByTestId('artifact-open-task'))
    await waitFor(() =>
      expect(screen.getByTestId('ort').getAttribute('data-ziel')).toBe('/chat?session=s1&replay=1'),
    )
  })

  it('zeigt keinen Rückweg, wo keine Sitzung genannt ist', async () => {
    api.getArtifact.mockResolvedValue(card({ session_id: '' }))
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )
    await screen.findByTestId('artifact-provenance')
    expect(screen.queryByTestId('artifact-open-task')).not.toBeInTheDocument()
  })
})

// A5 edge: the read that fails is not a dead end — the sentence and the reason
// stay, and a retry under them asks the same route again.
describe('the read failure names the next step', () => {
  const zeigeDetail = () =>
    render(
      <MemoryRouter>
        <ArtifactDetailPane id="a1" onChanged={() => {}} />
      </MemoryRouter>,
    )

  it('keeps the reason and offers the retry under the sentence', async () => {
    api.getArtifact.mockRejectedValueOnce(new Error('503 from /api/artifacts/a1'))
    zeigeDetail()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('artifacts.page.detailFailed')
    expect(alert.textContent).toContain('503')
    expect(screen.getByTestId('artifact-detail-retry').textContent).toBe('agentPanel.retry')
  })

  it('brings the card back on the press and clears the alert', async () => {
    api.getArtifact.mockRejectedValueOnce(new Error('503')).mockResolvedValueOnce(card())
    zeigeDetail()
    fireEvent.click(await screen.findByTestId('artifact-detail-retry'))
    expect(await screen.findByTestId('artifact-detail-adopt')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(api.getArtifact).toHaveBeenCalledTimes(2)
  })
})
