/**
 * WS3-17 — the workbench's finish (visual pass).
 *
 * The page answered the focus question three ways at once: the `.focus-ring`
 * class on its search field, the long inline outline form on back and retry, and
 * nothing at all on the tabs, the export link, the kind chips and the scope
 * clear. The long form only restates the global `*:focus-visible` rule, so the
 * page declared one treatment and then contradicted it. This file holds the page
 * on the treatment it already owns: every control carries `.focus-ring`, and the
 * inline form does not come back.
 *
 * It also pins the two places the pass changed the frame rather than the class:
 * the empty detail column now fills its place instead of floating as a stub, and
 * the loading list rows take the row height the loaded list already uses, so the
 * list does not jump when the rows arrive.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { render, screen, within, cleanup } from '@testing-library/react'
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

// Read from the config root, as globals.focus.test.ts does — jsdom hands out a
// non-file import.meta.url, so the URL form the parity test uses does not resolve.
const SRC = readFileSync('src/pages/ArtifactsPage.tsx', 'utf-8')

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

const deck = { ...card, id: 'b2', root_id: 'b2', name: 'plan.pptx', kind: 'pptx' }

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/artifacts']}>
      <Routes>
        <Route path="/artifacts" element={<ArtifactsPage />} />
        <Route path="/artifacts/:view" element={<ArtifactsPage />} />
      </Routes>
    </MemoryRouter>,
  )

const ringed = (el: Element) => el.className.includes('focus-ring')

beforeEach(() => {
  vi.clearAllMocks()
  api.listArtifactVersions.mockResolvedValue({ versions: [] })
  api.listArtifactExpiry.mockResolvedValue({ due: [], count: 0, bytes: 0, days: 30 })
  api.artifactPreview.mockResolvedValue({ mode: 'none', reason: 'no-text-preview' })
  api.artifactProvenance.mockResolvedValue({ known: false, calls: [] })
  api.getArtifact.mockResolvedValue(card)
  api.favoriteArtifact.mockImplementation(async (id: string) => ({ id, favorite: true }))
  api.removeArtifact.mockImplementation(async (id: string) => ({
    deleted: id,
    file_removed: false,
  }))
  api.listArtifacts.mockResolvedValue({ artifacts: [card, deck], total: 2 })
  api.artifactStats.mockResolvedValue({
    count: 2,
    bytes: 4096,
    by_kind: [],
    expiring_count: 0,
    expiring_bytes: 0,
    next_expiry: null,
  })
})

afterEach(cleanup)

describe('WS3-17 — the workbench keeps one focus treatment', () => {
  it('carries no second outline form beside the ring', () => {
    expect(SRC).not.toContain('focus-visible:outline-2')
  })

  it('rings the back control, the tabs and the export link alike', async () => {
    renderPage()
    await screen.findByTestId('artifact-select-a1')
    expect(ringed(screen.getByTestId('artifacts-back'))).toBe(true)
    expect(ringed(screen.getByRole('link', { name: /artifacts\.page\.view\.ablage/ }))).toBe(true)
    expect(ringed(screen.getByRole('link', { name: 'artifacts.exportAll' }))).toBe(true)
  })

  it('rings every kind chip in the filter group', async () => {
    renderPage()
    await screen.findByTestId('artifact-select-a1')
    const chips = within(screen.getByTestId('artifacts-kind-filter')).getAllByRole('button')
    expect(chips.length).toBeGreaterThanOrEqual(3)
    expect(chips.every((chip) => ringed(chip))).toBe(true)
  })

  it('rings the failure retry instead of re-declaring the outline', async () => {
    api.listArtifacts.mockRejectedValue(new Error('503 from /api/artifacts'))
    renderPage()
    const retry = await screen.findByTestId('artifacts-retry')
    expect(ringed(retry)).toBe(true)
    expect(retry.className).not.toContain('focus-visible:outline-2')
  })
})

describe('WS3-17 — the frame around the states', () => {
  it('lets the empty detail column fill its place', async () => {
    api.listArtifacts.mockResolvedValue({ artifacts: [], total: 0 })
    renderPage()
    await screen.findByTestId('artifacts-shelf-empty')
    // The explanation is said once (in the shelf); the detail column carries a
    // different, useful line about what appears there.
    expect(screen.getAllByText('artifacts.page.empty')).toHaveLength(1)
    const placeholder = screen
      .getAllByText('artifacts.page.detailEmpty')
      .find((el) => el.className.includes('border-dashed'))
    expect(placeholder).toBeTruthy()
    expect(placeholder!.className).toContain('h-full')
    expect(placeholder!.className).toContain('items-center')
  })

  it('keeps the loading rows on the loaded list row height', () => {
    // The loaded row is min-h-9 (libraryRow.tsx); the skeleton used to be a
    // py-1.5 box, so the column shrank when the data arrived.
    expect(SRC).toContain('flex min-h-9 items-center gap-2 px-2"')
  })
})
