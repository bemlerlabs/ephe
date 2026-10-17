// R4/A1: adopting is a gesture with a target. No target remembered → the card
// asks (422); someone else's file → it is left alone (409).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import ArtifactLibraryRow from './libraryRow'
import { ApiError, type ArtifactEntry } from '@/lib/api'

beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(cleanup)

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string) => k,
    i18n: { language: 'de' },
  }),
}))

const adoptArtifact = vi.fn()
const favoriteArtifact = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...real,
    adoptArtifact: (id: string, destination = '') => adoptArtifact(id, destination),
    favoriteArtifact: (id: string, favorite: boolean) => favoriteArtifact(id, favorite),
  }
})

const entry = (over: Partial<ArtifactEntry> = {}): ArtifactEntry => ({
  id: 'art1',
  root_id: 'art1',
  version: 1,
  session_id: 's1',
  name: 'bericht.pdf',
  path: '/tmp/ephe-home/artifacts/s1/bericht.pdf',
  kind: 'pdf',
  size: 2048,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: [],
  ...over,
})

const row = (art = entry()) =>
  render(<ArtifactLibraryRow art={art} selected onSelect={() => {}} onFavorite={() => {}} />)

describe('ArtifactLibraryRow', () => {
  it('zeigt Namen, Version und die drei Gesten', () => {
    row(entry({ name: 'deck.pptx', kind: 'pptx', version: 3 }))
    expect(screen.getByText('deck.pptx')).toBeTruthy()
    expect(screen.getByText('v3')).toBeTruthy()
    expect(screen.getByLabelText('artifacts.adopt: deck.pptx')).toBeTruthy()
    const download = screen.getByLabelText('artifacts.download: deck.pptx') as HTMLAnchorElement
    expect(download.getAttribute('href')).toContain('/api/artifacts/art1/file?download=1')
  })

  it('nennt das Ziel, nachdem es übernommen hat', async () => {
    adoptArtifact.mockResolvedValue({
      id: 'art1',
      adopted_path: '/Users/x/Dokumente/bericht.pdf',
      content_hash: 'sha256:a',
      adopted_hash: 'sha256:a',
      size: 2048,
    })
    row()
    fireEvent.click(screen.getByTestId('artifact-adopt-art1'))
    const state = await screen.findByTestId('artifact-adopt-state-art1')
    expect(state.textContent).toBe('/Users/x/Dokumente/bericht.pdf')
    expect(adoptArtifact).toHaveBeenCalledWith('art1', '')
  })

  it('fragt nach dem Ziel, wenn Ephe keines gemerkt hat', async () => {
    adoptArtifact.mockRejectedValueOnce(new ApiError('no destination', 422)).mockResolvedValue({
      id: 'art1',
      adopted_path: '/Users/x/Desktop/bericht.pdf',
      content_hash: 'sha256:a',
      adopted_hash: 'sha256:a',
      size: 2048,
    })
    row()
    fireEvent.click(screen.getByTestId('artifact-adopt-art1'))
    const input = await screen.findByLabelText('artifacts.adoptDestination')
    fireEvent.change(input, { target: { value: '~/Desktop' } })
    fireEvent.click(screen.getByTestId('artifact-adopt-go-art1'))
    await waitFor(() => expect(adoptArtifact).toHaveBeenLastCalledWith('art1', '~/Desktop'))
    expect((await screen.findByTestId('artifact-adopt-state-art1')).textContent).toBe(
      '/Users/x/Desktop/bericht.pdf',
    )
  })

  it('überschreibt keine fremde Datei, sondern sagt es', async () => {
    adoptArtifact.mockRejectedValue(new ApiError('wichtig.docx exists', 409))
    row()
    fireEvent.click(screen.getByTestId('artifact-adopt-art1'))
    const state = await screen.findByTestId('artifact-adopt-state-art1')
    expect(state.textContent).toContain('artifacts.adoptFailed')
    expect(state.textContent).toContain('wichtig.docx exists')
  })

  it('sterne um, ohne die Karte auszuwählen', async () => {
    const onFavorite = vi.fn()
    favoriteArtifact.mockResolvedValue({ id: 'art1', favorite: true })
    render(
      <ArtifactLibraryRow
        art={entry()}
        selected={false}
        onSelect={() => {}}
        onFavorite={onFavorite}
      />,
    )
    fireEvent.click(screen.getByLabelText('artifacts.favorite'))
    await waitFor(() => expect(favoriteArtifact).toHaveBeenCalledWith('art1', true))
    expect(onFavorite).toHaveBeenCalled()
  })
})

/**
 * R5 leftovers, finding 1: six cards named `file-summary.pdf` stood under each
 * other on the shelf, separated only by a clock time. The topic carries no weight
 * here — in 36 of 36 workbench rows `topic` is the file name — and the version
 * counter counts lines of the same root, not different births (1 of 36 rows has
 * version > 1). What tells the cards apart is their assignment; its short tag is
 * already shown in the provenance on the right, so the row itself can carry it.
 */
describe('Herkunftskürzel bei gleichnamigen Karten (R5-Reste/Befund 1)', () => {
  const zeile = (art: ArtifactEntry, ambiguous = false) =>
    render(
      <ArtifactLibraryRow
        art={art}
        selected={false}
        onSelect={() => {}}
        onFavorite={() => {}}
        ambiguous={ambiguous}
      />,
    )

  it('bleibt unsichtbar, solange der Name in der Gruppe einmalig ist', () => {
    zeile(entry({ turn_id: 'a1b2c3d4e5f6' }))
    expect(screen.queryByTestId('artifact-origin-art1')).toBeNull()
  })

  it('trennt gleichnamige Karten mit der Kurz-Kennung des Auftrags', () => {
    zeile(entry({ name: 'file-summary.pdf', turn_id: 'a1b2c3d4e5f6' }), true)
    const tag = screen.getByTestId('artifact-origin-art1')
    expect(tag.textContent).toBe('#a1b2c3d4')
    expect(tag.getAttribute('title')).toBe('a1b2c3d4e5f6')
  })

  it('fällt auf die Geburtssitzung zurück, wo kein Werkzeugruf gemerkt ist', () => {
    zeile(entry({ name: 'file-summary.pdf', session_id: 'ob-g3-r1-1790110990', turn_id: '' }), true)
    const tag = screen.getByTestId('artifact-origin-art1')
    expect(tag.textContent).toBe('#ob-g3-r1')
    expect(tag.getAttribute('title')).toBe('ob-g3-r1-1790110990')
  })

  it('sagt gar nichts, wenn die Karte weder Ruf noch Sitzung trägt', () => {
    zeile(entry({ name: 'file-summary.pdf', session_id: '', turn_id: '' }), true)
    expect(screen.queryByTestId('artifact-origin-art1')).toBeNull()
  })
})
