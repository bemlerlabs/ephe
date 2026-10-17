/**
 * B1 of the 2026-10-10 persona audit, held where the user reads it: a memory
 * store that does not answer must never be renderable as a store that holds
 * nothing. Reading, unreadable and empty are three states and each gets its own
 * assertion here, because one sentence standing in for another was the defect.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const api = vi.hoisted(() => ({
  listMemory: vi.fn(),
  searchMemory: vi.fn(),
  listDeletedMemory: vi.fn(),
  getMemoryStats: vi.fn(),
  deleteMemoryEntry: vi.fn(),
  updateMemoryEntry: vi.fn(),
  supersedeMemoryEntry: vi.fn(),
  restoreMemoryEntry: vi.fn(),
  migrateMemory: vi.fn(),
  setMemoryProvider: vi.fn(),
}))

vi.mock('@/lib/api', () => api)
vi.mock('@/lib/toast', () => ({ toastBus: { success: vi.fn(), error: vi.fn() } }))

import MemoryPage from './MemoryPage'

/** The 503 detail the route sends when its provider does not answer. */
const UNREADABLE = new Error("memory store 'kepta-bridge' did not answer (RuntimeError)")

const ROW = { id: 'a1b2c3', text: 'The gateway listens on 8765', metadata: {} }
const STATS = {
  total: 1,
  scope: 'ephe_memory_3f2a1b90c4d5',
  provider: 'kepta',
  reason: 'record',
  vector_leg: true,
  lexical_leg: true,
  deleted: 0,
}

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
  api.searchMemory.mockResolvedValue({ results: [] })
  api.listDeletedMemory.mockResolvedValue({ entries: [], total: 0 })
  api.getMemoryStats.mockResolvedValue(STATS)
  api.setMemoryProvider.mockResolvedValue({ provider: 'kepta', reason: '', scope: '' })
  api.migrateMemory.mockResolvedValue({})
})

describe('MemoryPage with an unreachable store', () => {
  it('names the state and never the empty sentence', async () => {
    api.listMemory.mockRejectedValue(UNREADABLE)
    renderAt()
    const alert = await screen.findByTestId('memory-unreachable')
    expect(alert).toHaveTextContent('memory.unreachable')
    expect(screen.queryByTestId('memory-page-empty')).toBeNull()
    expect(alert.getAttribute('role')).toBe('alert')
  })

  it('holds no count and carries the reason the route sent', async () => {
    api.listMemory.mockRejectedValue(UNREADABLE)
    renderAt()
    // The bare 0 was the number a user read as "Ephe remembers nothing".
    const count = await screen.findByTestId('memory-page-count')
    expect(count.textContent).toBe('—')
    expect(screen.getByTestId('memory-unreachable-reason').textContent).toContain('kepta-bridge')
  })

  it('answers the trash endpoint with the same state', async () => {
    api.listDeletedMemory.mockRejectedValue(UNREADABLE)
    renderAt('/memory/papierkorb')
    expect(await screen.findByTestId('memory-unreachable')).toBeTruthy()
    expect(screen.queryByTestId('memory-page-empty')).toBeNull()
  })

  it('retries on the same path and shows the holdings once the store answers', async () => {
    api.listMemory.mockRejectedValueOnce(UNREADABLE).mockResolvedValue({ entries: [ROW], total: 1 })
    renderAt()
    await screen.findByTestId('memory-unreachable')
    fireEvent.click(screen.getByRole('button', { name: 'agentPanel.retry' }))
    await waitFor(() => expect(api.listMemory).toHaveBeenCalledTimes(2))
    await screen.findByTestId('memory-row-0')
    expect(screen.queryByTestId('memory-unreachable')).toBeNull()
    expect(screen.getByTestId('memory-page-count').textContent).toBe('1')
  })
})

describe('MemoryPage with a store that answers', () => {
  it('keeps the empty sentence for the store that holds nothing', async () => {
    api.listMemory.mockResolvedValue({ entries: [], total: 0 })
    renderAt()
    expect(await screen.findByTestId('memory-page-empty')).toHaveTextContent('memory.empty')
    expect(screen.queryByTestId('memory-unreachable')).toBeNull()
    expect(screen.getByTestId('memory-page-count').textContent).toBe('0')
  })

  it('says it is reading while the request is still open', async () => {
    type ListResult = { entries: (typeof ROW)[]; total: number }
    let release: (value: ListResult) => void = () => {}
    api.listMemory.mockImplementation(
      () =>
        new Promise<ListResult>((resolve) => {
          release = resolve
        }),
    )
    renderAt()
    expect(await screen.findByText('memory.loading')).toBeTruthy()
    expect(screen.queryByTestId('memory-unreachable')).toBeNull()
    expect(screen.queryByTestId('memory-page-empty')).toBeNull()
    release({ entries: [ROW], total: 1 })
    await screen.findByTestId('memory-row-0')
  })
})
