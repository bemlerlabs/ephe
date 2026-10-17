/**
 * WD-31 integration pin: a data page that throws while rendering its rows must not
 * take the app with it.
 *
 * The shelf is the row renderer. A payload it cannot read used to throw straight to
 * the app-root boundary, so the whole shell became the crash screen. Here the exact
 * routing shape App uses (PageErrorBoundary around the page) is rendered: the shelf
 * throws, and what the user must still get is the page-scoped fallback with a retry
 * and a way back to the chat — not a blank app.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

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

// The row renderer refuses the payload it was handed.
vi.mock('@/components/dashboard/artifacts/shelf', () => ({
  default: () => {
    throw new Error('shelf could not read the payload')
  },
  kindLabel: (k: string) => k,
}))

import ArtifactsPage from './ArtifactsPage'
import PageErrorBoundary from '@/components/dashboard/PageErrorBoundary'

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

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  api.listArtifactVersions.mockResolvedValue({ versions: [] })
  api.listArtifactExpiry.mockResolvedValue({ due: [], count: 0, bytes: 0, days: 30 })
  api.artifactPreview.mockResolvedValue({ mode: 'none', reason: 'no-text-preview' })
  api.artifactProvenance.mockResolvedValue({ known: false, calls: [] })
  api.getArtifact.mockResolvedValue(card)
  api.artifactStats.mockResolvedValue({
    count: 1,
    bytes: 2048,
    by_kind: [],
    expiring_count: 0,
    expiring_bytes: 0,
    next_expiry: null,
  })
  api.listArtifacts.mockResolvedValue({ artifacts: [card], total: 1 })
})

afterEach(() => vi.restoreAllMocks())

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/artifacts']}>
      <Routes>
        <Route
          path="/artifacts"
          element={
            <PageErrorBoundary>
              <ArtifactsPage />
            </PageErrorBoundary>
          }
        />
      </Routes>
    </MemoryRouter>,
  )

describe('ArtifactsPage behind a page error boundary', () => {
  it('contains a render crash in the page instead of blanking the app', async () => {
    renderPage()
    // The page never commits its own frame; the boundary's fallback stands in its place.
    expect(await screen.findByTestId('page-error')).toBeTruthy()
    expect(screen.queryByTestId('artifacts-page')).toBeNull()
  })

  it('still hands the user a retry and a way back to the chat', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('page-error')).toBeTruthy())
    expect(screen.getByTestId('page-error-retry').textContent).toBe('error.crashRetry')
    expect(screen.getByTestId('page-error-home').getAttribute('href')).toBe('#/chat')
  })
})
