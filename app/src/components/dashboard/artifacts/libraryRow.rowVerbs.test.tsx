/**
 * The shelf row's verbs each carry a name a person can reach, and a touch floor.
 *
 * Measured 2026-10-10 at 390x844 on the dev surface: favourite, adopt and download
 * were 22x22 and their words lived only in a `title`, which never renders on a
 * phone. The row now follows the split the memory row already uses
 * (`agent/memoryRowCard.tsx`): the verb a glyph cannot carry — adopt, which is a
 * copy Ephe remembers, not a download — shows its word, the two well-known glyphs
 * keep aria-label plus tooltip. Every one of them takes the `max-lg:min-h-11`
 * mobile height, which is the part a jsdom render cannot measure: the 44 px is
 * proven by the Playwright run, this file holds the contract that keeps it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import ArtifactLibraryRow from './libraryRow'
import type { ArtifactEntry } from '@/lib/api'

beforeEach(() => {
  document.body.innerHTML = ''
})
afterEach(cleanup)

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...real,
    favoriteArtifact: vi.fn(),
    adoptArtifact: vi.fn(),
  }
})

const entry = (over: Partial<ArtifactEntry> = {}): ArtifactEntry => ({
  id: 'art1',
  root_id: 'art1',
  version: 1,
  session_id: 's1',
  name: 'report.pdf',
  path: '/tmp/ephe-home/artifacts/s1/report.pdf',
  kind: 'pdf',
  size: 2048,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: [],
  ...over,
})

function renderRow() {
  render(<ArtifactLibraryRow art={entry()} selected onSelect={() => {}} onFavorite={() => {}} />)
  return {
    favourite: screen.getByRole('button', { name: 'artifacts.favorite' }),
    adopt: screen.getByRole('button', { name: 'artifacts.adopt: report.pdf' }),
    download: screen.getByRole('link', { name: 'artifacts.download: report.pdf' }),
  }
}

describe('shelf row verbs', () => {
  it('names every verb through its accessible name', () => {
    const { favourite, adopt, download } = renderRow()
    for (const el of [favourite, adopt, download]) {
      expect(el.getAttribute('aria-label')).toBeTruthy()
    }
  })

  it('keeps the tooltip on the two verbs that stay icon-only', () => {
    const { favourite, download } = renderRow()
    expect(favourite.getAttribute('title')).toBe('artifacts.favorite')
    expect(download.getAttribute('title')).toBe('artifacts.downloadHint')
  })

  it('shows the adopt verb as a word, not only as a glyph', () => {
    const { adopt } = renderRow()
    expect(adopt.textContent).toContain('artifacts.adopt')
  })

  it('carries the mobile hit-area utility on all three verbs', () => {
    const { favourite, adopt, download } = renderRow()
    for (const el of [favourite, adopt, download]) {
      expect(el.className).toMatch(/max-lg:min-h-11/)
    }
  })

  it('does not let the row name double as the only label of the select control', () => {
    render(
      <ArtifactLibraryRow
        art={entry()}
        selected={false}
        onSelect={() => {}}
        onFavorite={() => {}}
      />,
    )
    expect(screen.getByTestId('artifact-select-art1').textContent).toContain('report.pdf')
  })
})
