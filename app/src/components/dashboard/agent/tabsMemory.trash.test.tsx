/**
 * MemoryTab — the trash view and the store's own source vocabulary.
 *
 * GIVEN  a memory surface whose store keeps deleted entries
 * WHEN   the trash opens with entries, with none, or under a store that
 *        deletes without keeping anything to restore
 * THEN   restore, in-trash filtering and the empty-state reason report what
 *        the store says, never a friendlier guess
 */
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryTab } from './tabsMemory'

// The memory surface talks only through @/lib/api — fully mocked, so that the
// test ids (real vs. synthetic) stay the only variable.
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

// t() returns the key plus its interpolated variables — tests then assert on
// "key:var=value" without simulating the real interpolation.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const parts = Object.entries(opts ?? {})
        .filter(([, v]) => typeof v === 'string' || typeof v === 'number')
        .map(([k, v]) => `${k}=${v}`)
      return parts.length ? `${key}:${parts.join(',')}` : key
    },
  }),
}))

const NOW_SEC = 1_790_000_000

function entry(
  over: Partial<{ id: string; text: string; metadata: Record<string, unknown> }> = {},
) {
  return {
    id: 'id-1',
    text: 'The deploy server runs on port 8765',
    metadata: { source: 'auto_memory', timestamp: NOW_SEC - 3600, hits: 1 },
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.setSystemTime(new Date(NOW_SEC * 1000))
  api.listMemory.mockResolvedValue({ entries: [entry()], total: 1 })
  api.searchMemory.mockResolvedValue({ results: [], query: '' })
  api.deleteMemoryEntry.mockResolvedValue({ deleted: 'id-1' })
  api.updateMemoryEntry.mockResolvedValue({ updated: 'id-1' })
  api.supersedeMemoryEntry.mockResolvedValue({ stored: true, id: 'id-2' })
  api.listDeletedMemory.mockResolvedValue({ entries: [], total: 0 })
  api.restoreMemoryEntry.mockResolvedValue({ restored: 'id-1' })
  api.getMemoryStats.mockResolvedValue({ total: 1, provider: 'kepta', deleted: 0 })
})

describe('MemoryTab trash and source labels', () => {
  it('opens the trash and restores what was forgotten', async () => {
    api.getMemoryStats.mockResolvedValue({ total: 1, provider: 'kepta', deleted: 2 })
    api.listDeletedMemory.mockResolvedValue({
      entries: [
        entry({
          id: 'gone-1',
          text: 'Accidentally deleted fact',
          metadata: { timestamp: NOW_SEC - 7200, deleted_at: NOW_SEC - 60 },
        }),
      ],
      total: 1,
    })
    render(<MemoryTab />)
    const toggle = await screen.findByTestId('memory-trash-toggle')
    expect(toggle.textContent).toContain('2')
    fireEvent.click(toggle)
    const row = await screen.findByTestId('memory-row-0')
    expect(row.textContent).toContain('Accidentally deleted fact')
    fireEvent.click(screen.getByTestId('memory-restore-0'))
    await waitFor(() => expect(api.restoreMemoryEntry).toHaveBeenCalledWith('gone-1'))
  })

  it('says so when the brain has no trash instead of showing an empty lie', async () => {
    api.getMemoryStats.mockResolvedValue({ total: 3, provider: 'chroma', deleted: 0 })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.queryByTestId('memory-trash-toggle')).toBeNull()
    expect(screen.getByTestId('memory-provider').textContent).toContain('chroma')
  })

  // D5 live finding: the last trash entry was restored, the statistics report 0 —
  // and the surface sat in an empty view with no way back.
  it('keeps the way out of the trash when the last entry is restored', async () => {
    api.getMemoryStats
      .mockResolvedValueOnce({ total: 1, provider: 'kepta', deleted: 1 })
      .mockResolvedValue({ total: 2, provider: 'kepta', deleted: 0 })
    api.listDeletedMemory.mockResolvedValue({
      entries: [
        entry({
          id: 'gone-1',
          text: 'Accidentally deleted fact',
          metadata: { timestamp: NOW_SEC - 7200, deleted_at: NOW_SEC - 60 },
        }),
      ],
      total: 1,
    })
    render(<MemoryTab />)
    fireEvent.click(await screen.findByTestId('memory-trash-toggle'))
    fireEvent.click(await screen.findByTestId('memory-restore-0'))
    await waitFor(() => expect(api.restoreMemoryEntry).toHaveBeenCalledWith('gone-1'))
    const toggle = await screen.findByTestId('memory-trash-toggle')
    expect(toggle.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(toggle)
    await waitFor(() =>
      expect(screen.getByTestId('memory-row-0').textContent).toContain('The deploy server'),
    )
  })

  it('labels every origin from the store vocabulary, not only its own two', async () => {
    // Walkthrough 2026-10-12: 32 rows, 29 chips — the `agent` twin carried no
    // label because the page's own map knew only `auto_memory` and `compaction`.
    api.listMemory.mockResolvedValue({
      entries: [
        entry({
          id: 'agent-1',
          text: 'Written by the tool',
          metadata: { source: 'agent', timestamp: NOW_SEC - 60 },
        }),
      ],
      total: 1,
    })
    api.getMemoryStats.mockResolvedValue({
      total: 1,
      provider: 'chroma',
      deleted: 0,
      sources: {
        auto_memory: 'From chat',
        compaction: 'Compacted',
        agent: 'Agent tool',
        user: 'Added by hand',
      },
    })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-source-0').textContent).toBe('Agent tool')
  })

  it('stops offering a restore under a store that deletes finally', async () => {
    api.getMemoryStats.mockResolvedValue({ total: 3, provider: 'chroma', deleted: 1 })
    api.listDeletedMemory.mockResolvedValue({
      entries: [
        entry({
          id: 'gone-1',
          text: 'Gone for good',
          metadata: { timestamp: NOW_SEC - 60 },
        }),
      ],
      total: 1,
      restore_supported: false,
      detail: "the active store 'chroma' deletes finally: nothing is kept to restore.",
    })
    render(<MemoryTab />)
    fireEvent.click(await screen.findByTestId('memory-trash-toggle'))
    await screen.findByTestId('memory-row-0')
    expect(screen.queryByTestId('memory-restore-0')).toBeNull()
  })

  it('names why the trash stays empty instead of promising what it holds', async () => {
    api.getMemoryStats.mockResolvedValue({ total: 3, provider: 'chroma', deleted: 1 })
    api.listDeletedMemory.mockResolvedValue({
      entries: [],
      total: 0,
      restore_supported: false,
      detail: "the active store 'chroma' deletes finally: nothing is kept to restore.",
    })
    render(<MemoryTab />)
    fireEvent.click(await screen.findByTestId('memory-trash-toggle'))
    expect(await screen.findByText(/deletes finally/)).toBeTruthy()
    expect(screen.queryByText('agentPanel.memoryTrashEmpty')).toBeNull()
  })

  it('searches inside the trash instead of ignoring the query', async () => {
    api.getMemoryStats.mockResolvedValue({ total: 1, provider: 'kepta', deleted: 2 })
    const kept = entry({
      id: 'gone-1',
      text: 'The move to Zurich',
      metadata: { timestamp: NOW_SEC - 7200, deleted_at: NOW_SEC - 60 },
    })
    const other = entry({
      id: 'gone-2',
      text: 'The deploy server runs on port 8765',
      metadata: { timestamp: NOW_SEC - 7200, deleted_at: NOW_SEC - 30 },
    })
    api.listDeletedMemory.mockResolvedValue({ entries: [kept, other], total: 2 })
    render(<MemoryTab />)
    fireEvent.click(await screen.findByTestId('memory-trash-toggle'))
    await screen.findByTestId('memory-row-1')
    fireEvent.change(screen.getByTestId('memory-search'), { target: { value: 'Zurich' } })
    // Both halves in one wait: the held query still shows the unfiltered pair.
    await waitFor(() => {
      expect(screen.getByTestId('memory-row-0').textContent).toContain(kept.text)
      expect(screen.queryByTestId('memory-row-1')).toBeNull()
    })
    fireEvent.change(screen.getByTestId('memory-search'), { target: { value: 'Bitcoin' } })
    await waitFor(() => expect(screen.getByText('agentPanel.memoryTrashNoMatch')).toBeTruthy())
  })
})
