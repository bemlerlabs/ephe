/**
 * The panel tab reads the same store through the same hook, so it owes the user
 * the same sentence (B1). Held apart from the page test because the tab is the
 * surface a user sees first while a turn is running.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryTab } from './tabsMemory'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const api = vi.hoisted(() => ({
  listMemory: vi.fn(),
  searchMemory: vi.fn(),
  deleteMemoryEntry: vi.fn(),
  updateMemoryEntry: vi.fn(),
  supersedeMemoryEntry: vi.fn(),
  listDeletedMemory: vi.fn(),
  restoreMemoryEntry: vi.fn(),
  getMemoryStats: vi.fn(),
}))
vi.mock('@/lib/api', () => ({
  listMemory: api.listMemory,
  searchMemory: api.searchMemory,
  deleteMemoryEntry: api.deleteMemoryEntry,
  updateMemoryEntry: api.updateMemoryEntry,
  supersedeMemoryEntry: api.supersedeMemoryEntry,
  listDeletedMemory: api.listDeletedMemory,
  restoreMemoryEntry: api.restoreMemoryEntry,
  getMemoryStats: api.getMemoryStats,
}))

const UNREADABLE = new Error("memory store 'kepta' did not answer (OperationalError)")
const ROW = { id: 'id-1', text: 'The gateway listens on 8765', metadata: {} }

beforeEach(() => {
  vi.clearAllMocks()
  api.searchMemory.mockResolvedValue({ results: [] })
  api.listDeletedMemory.mockResolvedValue({ entries: [], total: 0 })
  api.getMemoryStats.mockResolvedValue({ total: 1, provider: 'kepta', deleted: 0 })
})

describe('MemoryTab with an unreachable store', () => {
  it('replaces the empty illustration with the state and a way back', async () => {
    api.listMemory.mockRejectedValue(UNREADABLE)
    render(<MemoryTab />)
    const alert = await screen.findByTestId('memory-unreachable')
    expect(alert).toHaveTextContent('memory.unreachable')
    expect(screen.queryByText('agentPanel.memoryEmpty')).toBeNull()
    expect(alert.getAttribute('role')).toBe('alert')
  })

  it('counts nothing it did not read', async () => {
    api.listMemory.mockRejectedValue(UNREADABLE)
    render(<MemoryTab />)
    const count = await screen.findByTestId('memory-count')
    expect(count.textContent).toBe('—')
  })

  it('lists the holdings again after a retry', async () => {
    api.listMemory.mockRejectedValueOnce(UNREADABLE).mockResolvedValue({ entries: [ROW], total: 1 })
    render(<MemoryTab />)
    await screen.findByTestId('memory-unreachable')
    fireEvent.click(screen.getByRole('button', { name: 'agentPanel.retry' }))
    await waitFor(() => expect(api.listMemory).toHaveBeenCalledTimes(2))
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-count').textContent).toBe('1')
  })
})
