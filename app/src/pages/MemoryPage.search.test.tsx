/**
 * D9: what the memory search says, and how often it asks.
 *
 * Two failures in one field. A word that matches nothing left the list untouched and
 * the count at its old number, so the search looked dead; and every keystroke went
 * straight to `GET /api/memory/search`, so one word cost six vector searches over
 * the whole store. The store ranks and never comes back empty, which is why the count
 * line now names the list it is showing.
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
  listMemory: vi.fn(),
  searchMemory: vi.fn(),
  listDeletedMemory: vi.fn(),
  getMemoryStats: vi.fn(),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  updateMemoryEntry: vi.fn(async () => ({ updated: '' })),
  supersedeMemoryEntry: vi.fn(async () => ({ stored: true, id: '' })),
  restoreMemoryEntry: vi.fn(async () => ({ restored: '' })),
  migrateMemory: vi.fn(),
  setMemoryProvider: vi.fn(async () => ({ provider: 'kepta', reason: '', scope: '' })),
}))

vi.mock('@/lib/api', () => api)
vi.mock('@/lib/toast', () => ({ toastBus: { success: vi.fn(), error: vi.fn() } }))

import MemoryPage from './MemoryPage'

const fact = (id: string, text: string) => ({
  id,
  text,
  metadata: { source: 'auto_memory', type: 'semantic' },
})

function renderAt(path = '/memory') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/memory/:view" element={<MemoryPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getMemoryStats.mockResolvedValue({
    total: 201,
    scope: 'ephe_memory_3f2a',
    provider: 'kepta',
    vector_leg: true,
    lexical_leg: true,
    deleted: 0,
  })
  api.listMemory.mockResolvedValue({
    entries: [
      fact('f1', 'Der Gateway läuft auf Port 8765'),
      fact('f2', 'Zürich liegt am Limmatquai'),
    ],
    total: 2,
  })
  // The store ranks its whole inventory: a nonsense word still answers with rows.
  api.searchMemory.mockResolvedValue({
    results: [
      { ...fact('f2', 'Zürich liegt am Limmatquai'), score: 0.5766 },
      { ...fact('f1', 'Der Gateway läuft auf Port 8765'), score: 0.571 },
    ],
    total: 2,
  })
  api.listDeletedMemory.mockResolvedValue({ entries: [], total: 0 })
  api.migrateMemory.mockResolvedValue({})
})

afterEach(cleanup)

const field = () => screen.getByTestId('memory-page-search')

describe('the memory search', () => {
  it('asks once for a typed word', async () => {
    renderAt()
    await screen.findByTestId('memory-page-count')
    let typed = ''
    for (const letter of 'Kaffee') {
      typed += letter
      fireEvent.change(field(), { target: { value: typed } })
    }
    expect(api.searchMemory).not.toHaveBeenCalled()
    await waitFor(() => expect(api.searchMemory).toHaveBeenCalledTimes(1))
    expect(api.searchMemory).toHaveBeenCalledWith('Kaffee', 200)
  })

  it('names the list a query produced instead of leaving the count alone', async () => {
    renderAt()
    await screen.findByTestId('memory-page-count')
    expect(screen.getByTestId('memory-page-count').textContent).toBe('2')
    fireEvent.change(field(), { target: { value: 'Zürich' } })
    const line = await screen.findByTestId('memory-page-count')
    await waitFor(() => expect(line.textContent).toContain('memory.searchRanking'))
    expect(line.textContent).toContain('"shown":"2"')
    expect(line.textContent).toContain('"total":"201"')
  })

  it('says nothing matched when the list really is empty', async () => {
    // The trash view filters by text, so this is the reachable case of a query that
    // answers with no rows.
    renderAt('/memory/papierkorb')
    await screen.findByTestId('memory-page-count')
    fireEvent.change(field(), { target: { value: 'qqzz' } })
    const empty = await screen.findByTestId('memory-page-empty')
    await waitFor(() => expect(empty.textContent).toBe('memory.noMatch'))
    expect(screen.queryByText('memory.emptyTrash')).toBeNull()
  })

  it('keeps the store-empty sentence when no query is set', async () => {
    renderAt('/memory/papierkorb')
    expect((await screen.findByTestId('memory-page-empty')).textContent).toBe('memory.emptyTrash')
  })
})
