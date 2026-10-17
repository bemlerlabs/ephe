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
    text: 'Der Deploy-Server läuft auf Port 8765',
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

describe('MemoryTab', () => {
  it('renders listed entries with their source and age', async () => {
    render(<MemoryTab />)
    const row = await screen.findByTestId('memory-row-0')
    expect(row.textContent).toContain('Der Deploy-Server läuft auf Port 8765')
    expect(screen.getByTestId('memory-source-0').textContent).toBe('agentPanel.memorySourceAuto')
    // timestamp -> a readable duration instead of the raw Unix seconds
    expect(screen.getByTestId('memory-age-0').textContent).toContain('agentPanel.memoryAge:')
  })

  it('labels a compaction-sourced entry differently from an auto-learned one', async () => {
    api.listMemory.mockResolvedValue({
      entries: [entry({ metadata: { source: 'compaction', timestamp: NOW_SEC - 60, hits: 1 } })],
      total: 1,
    })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-source-0').textContent).toBe(
      'agentPanel.memorySourceCompaction',
    )
  })

  it('surfaces retrieval hits and high priority, which drive eviction and injection order', async () => {
    api.listMemory.mockResolvedValue({
      entries: [
        entry({
          metadata: { source: 'auto_memory', timestamp: NOW_SEC - 60, hits: 7, priority: 'high' },
        }),
      ],
      total: 1,
    })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-hits-0').textContent).toContain('7')
    expect(screen.getByTestId('memory-priority-0').textContent).toBe(
      'agentPanel.memoryPriorityHigh',
    )
  })

  it('hides hits and priority chips when they carry no signal', async () => {
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.queryByTestId('memory-hits-0')).toBeNull()
    expect(screen.queryByTestId('memory-priority-0')).toBeNull()
  })

  // ── Regression: search hits must keep their real document id ──────

  it('deletes a search hit by its real document id, not a synthetic index', async () => {
    const hit = {
      id: '7cea238ff07c3120',
      text: 'Gefundener Fakt',
      score: 0.91,
      metadata: { source: 'auto_memory', timestamp: NOW_SEC - 60, hits: 1 },
    }
    api.searchMemory.mockResolvedValue({ results: [hit], query: 'Fakt' })
    render(<MemoryTab />)
    fireEvent.change(screen.getByTestId('memory-search'), { target: { value: 'Fakt' } })

    // The field holds the word for a moment before it asks (D9), and the list keeps
    // answering until then, so the row has to be waited for by its content.
    await waitFor(() => expect(screen.getByTestId('memory-row-0').textContent).toContain(hit.text))
    fireEvent.click(screen.getByTestId('memory-delete-0'))
    await waitFor(() => expect(api.deleteMemoryEntry).toHaveBeenCalledWith('7cea238ff07c3120'))
  })

  it('deletes a listed entry by its id', async () => {
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    fireEvent.click(screen.getByTestId('memory-delete-0'))
    await waitFor(() => expect(api.deleteMemoryEntry).toHaveBeenCalledWith('id-1'))
    // the list reloads after the deletion
    await waitFor(() => expect(api.listMemory).toHaveBeenCalledTimes(2))
  })

  // ── Editing ──────────────────────────────────────────────────────────────

  it('edits an entry inline and persists it through PUT', async () => {
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')

    fireEvent.click(screen.getByTestId('memory-edit-0'))
    const input = screen.getByTestId('memory-edit-input')
    fireEvent.change(input, { target: { value: 'Korrigiert: Port 9999' } })
    fireEvent.click(screen.getByTestId('memory-edit-rewrite'))

    await waitFor(() =>
      expect(api.updateMemoryEntry).toHaveBeenCalledWith('id-1', 'Korrigiert: Port 9999'),
    )
    await waitFor(() => expect(api.listMemory).toHaveBeenCalledTimes(2))
  })

  it('keeps the id when the search result is edited', async () => {
    const hit = {
      id: 'deadbeefcafe1234',
      text: 'Zu korrigieren',
      score: 0.8,
      metadata: { source: 'auto_memory', timestamp: NOW_SEC - 60, hits: 1 },
    }
    api.searchMemory.mockResolvedValue({ results: [hit], query: 'x' })
    render(<MemoryTab />)
    fireEvent.change(screen.getByTestId('memory-search'), { target: { value: 'x' } })
    await waitFor(() => expect(screen.getByTestId('memory-row-0').textContent).toContain(hit.text))

    fireEvent.click(screen.getByTestId('memory-edit-0'))
    fireEvent.change(screen.getByTestId('memory-edit-input'), { target: { value: 'Neu' } })
    fireEvent.click(screen.getByTestId('memory-edit-rewrite'))
    await waitFor(() =>
      expect(api.updateMemoryEntry).toHaveBeenCalledWith('deadbeefcafe1234', 'Neu'),
    )
  })

  it('cancels an edit without calling the API', async () => {
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')

    fireEvent.click(screen.getByTestId('memory-edit-0'))
    fireEvent.change(screen.getByTestId('memory-edit-input'), { target: { value: 'Unsaved' } })
    fireEvent.click(screen.getByTestId('memory-edit-cancel'))

    expect(api.updateMemoryEntry).not.toHaveBeenCalled()
    expect(api.supersedeMemoryEntry).not.toHaveBeenCalled()
    expect(screen.queryByTestId('memory-edit-input')).toBeNull()
    // the text stands there unchanged again
    expect(screen.getByTestId('memory-row-0').textContent).toContain('Port 8765')
  })

  it('does not submit a blank edit — that would silently destroy the entry', async () => {
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')

    fireEvent.click(screen.getByTestId('memory-edit-0'))
    const input = screen.getByTestId('memory-edit-input')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByTestId('memory-edit-rewrite'))
    fireEvent.click(screen.getByTestId('memory-edit-supersede'))

    expect(api.updateMemoryEntry).not.toHaveBeenCalled()
    expect(api.supersedeMemoryEntry).not.toHaveBeenCalled()
  })

  it('reports a failed save and leaves the row editable', async () => {
    api.updateMemoryEntry.mockRejectedValueOnce(new Error('boom'))
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')

    fireEvent.click(screen.getByTestId('memory-edit-0'))
    fireEvent.change(screen.getByTestId('memory-edit-input'), { target: { value: 'Neu' } })
    fireEvent.click(screen.getByTestId('memory-edit-rewrite'))

    await waitFor(() => expect(api.updateMemoryEntry).toHaveBeenCalled())
    expect(screen.getByTestId('memory-edit-input')).toBeTruthy()
  })

  // ── D5: the two write kinds are tellable apart in the UI ────────────────

  it('offers the correction as its own write kind, not as an overwrite', async () => {
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')

    fireEvent.click(screen.getByTestId('memory-edit-0'))
    fireEvent.change(screen.getByTestId('memory-edit-input'), {
      target: { value: 'Der Port ist 9100' },
    })
    fireEvent.click(screen.getByTestId('memory-edit-supersede'))

    await waitFor(() =>
      expect(api.supersedeMemoryEntry).toHaveBeenCalledWith('id-1', 'Der Port ist 9100'),
    )
    // superseding is a POST correction — the old entry stays, PUT would overwrite
    expect(api.updateMemoryEntry).not.toHaveBeenCalled()
  })

  it('marks a superseded fact and the correction that replaced it', async () => {
    api.listMemory.mockResolvedValue({
      entries: [
        entry({
          id: 'new-1',
          text: 'Der Gateway läuft auf Port 9100',
          metadata: { source: 'agent', timestamp: NOW_SEC - 60, supersedes: 'old-1' },
        }),
        entry({
          id: 'old-1',
          text: 'Der Gateway läuft auf Port 8765',
          metadata: {
            source: 'agent',
            timestamp: NOW_SEC - 3600,
            superseded_by: 'new-1',
            valid_to: NOW_SEC - 60,
          },
        }),
      ],
      total: 2,
    })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-lineage-0').textContent).toBe('agentPanel.memorySupersedes')
    // The superseded fact is visible as what it is, not quietly gone.
    expect(screen.getByTestId('memory-lineage-1').textContent).toBe('agentPanel.memorySuperseded')
  })

  it('shows the memory type, which is what makes procedural facts findable', async () => {
    api.listMemory.mockResolvedValue({
      entries: [
        entry({ metadata: { source: 'agent', timestamp: NOW_SEC - 60, type: 'procedural' } }),
      ],
      total: 1,
    })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-type-0').textContent).toBe('agentPanel.memoryTypeProcedural')
  })

  it('labels the answering brain so the storage choice is not folklore', async () => {
    render(<MemoryTab />)
    const pill = await screen.findByTestId('memory-provider')
    expect(pill.textContent).toContain('kepta')
  })

  // D5 live finding: inside the trash the search was ignored silently — typing
  // changed nothing, and an empty answer would be a lie, so the basket filters
  // itself. Second finding: four of five rows were dimmed because "has descent"
  // had been mistaken for "is history" — the correction leads, only the
  // superseded fact steps back.
  it('dims only the replaced fact, not the correction that leads', async () => {
    api.listMemory.mockResolvedValue({
      entries: [
        entry({ id: 'new-1', metadata: { timestamp: NOW_SEC - 60, supersedes: 'old-1' } }),
        entry({ id: 'old-1', metadata: { timestamp: NOW_SEC - 3600, superseded_by: 'new-1' } }),
      ],
      total: 2,
    })
    render(<MemoryTab />)
    await screen.findByTestId('memory-row-1')
    expect(screen.getByTestId('memory-row-0').className).not.toContain('opacity-70')
    expect(screen.getByTestId('memory-row-1').className).toContain('opacity-70')
  })
})
