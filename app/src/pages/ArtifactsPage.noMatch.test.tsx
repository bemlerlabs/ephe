/**
 * D8: a search that matches nothing must not report an empty workbench.
 *
 * Measured on the shipping build with 39 cards in the index: typing a word that is
 * on none of them left the header counting "39 artifacts" while the list column said
 * "Nothing in the workbench yet. Everything a tool creates lands here" and the detail
 * column asked for a card to pick. Both sentences are false in that state, and the
 * field that caused it had no way out shorter than backspace.
 *
 * The page owns the filters, so the page owns the sentence: the shelf keeps its own
 * empty state for a store that really is empty, and the filtered empty gets its own
 * string plus the clear action.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
      i18n: { language: 'en', changeLanguage: vi.fn() },
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

import ArtifactsPage from './ArtifactsPage'

const card = {
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
  expires_at: null,
  keep: false,
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/artifacts']}>
      <Routes>
        <Route path="/artifacts" element={<ArtifactsPage />} />
        <Route path="/artifacts/:view" element={<ArtifactsPage />} />
      </Routes>
    </MemoryRouter>,
  )

const searchField = () => screen.getByLabelText('artifacts.searchPlaceholder')

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
  api.getArtifact.mockResolvedValue(card)
  api.favoriteArtifact.mockImplementation(async (id: string) => ({ id, favorite: true }))
  api.removeArtifact.mockImplementation(async (id: string) => ({
    deleted: id,
    file_removed: false,
  }))
  // The index does the filtering, so a query that matches nothing answers with no
  // rows while the store behind it still holds its 39 cards.
  api.listArtifacts.mockImplementation(async ({ q }: { q: string }) => ({
    artifacts: q ? [] : [card],
    total: q ? 0 : 39,
  }))
  api.artifactStats.mockResolvedValue({
    count: 39,
    bytes: 194200,
    by_kind: [],
    expiring_count: 0,
    expiring_bytes: 0,
    next_expiry: null,
  })
})

afterEach(cleanup)

describe('a workbench search that matches nothing', () => {
  it('names the filter as the reason and keeps the store count with it', async () => {
    renderPage()
    await screen.findByTestId('artifact-select-a1')
    fireEvent.change(searchField(), { target: { value: 'zzz' } })
    const nomatch = await screen.findByTestId('artifacts-nomatch')
    expect(nomatch.textContent).toContain('artifacts.page.noMatchHidden')
    expect(nomatch.textContent).toContain('"count":"39"')
    expect(screen.queryByTestId('artifacts-shelf-empty')).toBeNull()
  })

  it('offers the way out and takes the filter away when used', async () => {
    renderPage()
    await screen.findByTestId('artifact-select-a1')
    fireEvent.change(searchField(), { target: { value: 'zzz' } })
    fireEvent.click(await screen.findByTestId('artifacts-clear-filters'))
    await waitFor(() => expect(searchField().getAttribute('value')).toBe(''))
    await waitFor(() =>
      expect(api.listArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ q: '' })),
    )
    await waitFor(() => expect(screen.queryByTestId('artifacts-nomatch')).toBeNull())
    expect(screen.getByTestId('artifact-select-a1')).toBeTruthy()
  })

  it('gives the field a named clear control only while it holds text', async () => {
    renderPage()
    await screen.findByTestId('artifact-select-a1')
    expect(screen.queryByTestId('artifacts-search-clear')).toBeNull()
    fireEvent.change(searchField(), { target: { value: 'zzz' } })
    const clear = await screen.findByTestId('artifacts-search-clear')
    expect(clear.getAttribute('aria-label')).toBe('artifacts.searchClear')
    expect(clear.getAttribute('title')).toBe('artifacts.searchClear')
    fireEvent.click(clear)
    await waitFor(() => expect(searchField().getAttribute('value')).toBe(''))
  })

  it('leaves the detail column without a card to pick', async () => {
    renderPage()
    await screen.findByTestId('artifact-select-a1')
    fireEvent.change(searchField(), { target: { value: 'zzz' } })
    await screen.findByTestId('artifacts-nomatch')
    expect(screen.queryByText('artifacts.page.pickCard')).toBeNull()
    expect(screen.getByText('artifacts.page.noMatch')).toBeTruthy()
  })

  it('still says the shelf is empty when the store is', async () => {
    api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
    renderPage()
    const empty = await screen.findByTestId('artifacts-shelf-empty')
    expect(empty.textContent).toBe('artifacts.page.empty')
    expect(screen.queryByTestId('artifacts-nomatch')).toBeNull()
    expect(screen.queryByTestId('artifacts-clear-filters')).toBeNull()
  })
})
