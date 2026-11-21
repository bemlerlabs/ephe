/**
 * F4: the workbench error has to end in something the user can press.
 *
 * The sentence was honest and the state was a dead end: no retry control, no reason,
 * and the header count gone with it, because the count's own read swallows its
 * failure. The retry is wired to the counter both reads key off, so one press brings
 * the list and the count back together.
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

beforeEach(() => {
  vi.clearAllMocks()
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
  api.listArtifacts.mockRejectedValue(new Error('503 from /api/artifacts'))
})

afterEach(cleanup)

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/artifacts']}>
      <Routes>
        <Route path="/artifacts" element={<ArtifactsPage />} />
        <Route path="/artifacts/:view" element={<ArtifactsPage />} />
      </Routes>
    </MemoryRouter>,
  )

describe('the workbench failure branch', () => {
  it('carries the reason the route sent', async () => {
    renderPage()
    const error = await screen.findByTestId('artifacts-error')
    expect(error.textContent).toContain('artifacts.page.failed')
    expect((await screen.findByTestId('artifacts-error-reason')).textContent).toContain('503')
  })

  it('offers the retry under the sentence', async () => {
    renderPage()
    const retry = await screen.findByTestId('artifacts-retry')
    expect(retry.textContent).toBe('agentPanel.retry')
  })

  it('brings the list and the header count back on one press', async () => {
    renderPage()
    const retry = await screen.findByTestId('artifacts-retry')
    await waitFor(() => expect(api.artifactStats).toHaveBeenCalledTimes(1))
    api.listArtifacts.mockResolvedValue({ artifacts: [card], total: 1 })
    fireEvent.click(retry)
    await waitFor(() => expect(api.listArtifacts).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(api.artifactStats).toHaveBeenCalledTimes(2))
    expect(await screen.findByTestId('artifact-select-a1')).toBeTruthy()
    expect(screen.queryByTestId('artifacts-error')).toBeNull()
    expect(screen.getByTestId('artifacts-stats').textContent).toContain('artifacts.page.stats')
  })
})
