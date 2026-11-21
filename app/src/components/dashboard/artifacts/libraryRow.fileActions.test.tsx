/**
 * N4 — the row's Finder verbs exist in the shell and nowhere else.
 *
 * A browser cannot reveal a file, so the two buttons are absent there; in the
 * shell they call the fenced commands with the artifact's own path and, when the
 * fence refuses (a copy outside the allowed roots), say so beside the row.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ArtifactEntry } from '@/lib/api'
import ArtifactLibraryRow from './libraryRow'

const { canUse, reveal, openDefault } = vi.hoisted(() => ({
  canUse: vi.fn(() => true),
  reveal: vi.fn(async () => true),
  openDefault: vi.fn(async () => true),
}))

vi.mock('@/lib/fileActions', () => ({
  canUseNativeFileActions: canUse,
  revealInFinder: reveal,
  openInDefaultApp: openDefault,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>()
  return { ...real, favoriteArtifact: vi.fn(), adoptArtifact: vi.fn() }
})

const ART: ArtifactEntry = {
  id: 'art1',
  root_id: 'art1',
  version: 1,
  session_id: 's1',
  name: 'report.pdf',
  path: '/Users/someone/.ephe/artifacts/s1/report.pdf',
  kind: 'pdf',
  size: 2048,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: [],
}

beforeEach(() => {
  canUse.mockReturnValue(true)
  reveal.mockClear()
  openDefault.mockClear()
  document.body.innerHTML = ''
})
afterEach(cleanup)

const row = () => (
  <ArtifactLibraryRow art={ART} selected={false} onSelect={() => {}} onFavorite={() => {}} />
)

describe('the artifact row in the desktop shell', () => {
  it('reveals the artifact through the shell command', async () => {
    render(row())

    fireEvent.click(screen.getByTestId('artifact-reveal-in-finder'))

    await waitFor(() => expect(reveal).toHaveBeenCalledWith(ART.path))
  })

  it('opens the artifact with its default app', async () => {
    render(row())

    fireEvent.click(screen.getByTestId('artifact-open-default'))

    await waitFor(() => expect(openDefault).toHaveBeenCalledWith(ART.path))
  })

  it('names a refusal beside the row instead of doing nothing', async () => {
    reveal.mockResolvedValue(false)
    render(row())

    fireEvent.click(screen.getByTestId('artifact-reveal-in-finder'))

    expect(await screen.findByRole('alert')).toHaveTextContent('artifacts.fileActionFailed')
  })
})

describe('the artifact row in a browser', () => {
  it('offers neither verb', () => {
    canUse.mockReturnValue(false)
    render(row())

    expect(screen.queryByTestId('artifact-reveal-in-finder')).toBeNull()
    expect(screen.queryByTestId('artifact-open-default')).toBeNull()
  })
})
