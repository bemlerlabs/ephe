/**
 * G7 provenance: the stored facts a past turn's prompt carried.
 *
 * GIVEN  a turn that carried injected memories
 * WHEN   it draws a chip, is tapped, and Retract is pressed
 * THEN   the chip speaks the fact, the editor opens on it, and Retract takes the
 *        delete path — never the supersede write
 *  AND   a turn with no memories (empty or absent) draws nothing at all.
 */
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TurnMemories } from './turnMemories'

// The block writes through @/lib/api only (via useMemoryActions) — fully mocked,
// so the test ids stay the only variable. Same shape as tabsMemory.test.tsx.
const api = vi.hoisted(() => ({
  deleteMemoryEntry: vi.fn(),
  updateMemoryEntry: vi.fn(),
  supersedeMemoryEntry: vi.fn(),
  restoreMemoryEntry: vi.fn(),
  listMemory: vi.fn(),
  searchMemory: vi.fn(),
  listDeletedMemory: vi.fn(),
  getMemoryStats: vi.fn(),
}))
vi.mock('@/lib/api', () => ({
  deleteMemoryEntry: api.deleteMemoryEntry,
  updateMemoryEntry: api.updateMemoryEntry,
  supersedeMemoryEntry: api.supersedeMemoryEntry,
  restoreMemoryEntry: api.restoreMemoryEntry,
  listMemory: api.listMemory,
  searchMemory: api.searchMemory,
  listDeletedMemory: api.listDeletedMemory,
  getMemoryStats: api.getMemoryStats,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const FACT = { id: 'm1', text: 'User prefers dark mode', score: 0.8, source: 'auto_memory' }

beforeEach(() => {
  vi.clearAllMocks()
  api.deleteMemoryEntry.mockResolvedValue({ deleted: 'm1' })
  api.updateMemoryEntry.mockResolvedValue({ updated: 'm1' })
  api.supersedeMemoryEntry.mockResolvedValue({ stored: true, id: 'm2' })
})

describe('TurnMemories (G7 provenance)', () => {
  it('draws one chip per memory, titled with the full fact', () => {
    render(<TurnMemories ti={0} memories={[FACT]} reload={vi.fn()} />)

    const chip = screen.getByTestId('turn-fact-0-0')
    expect(chip.textContent).toBe('User prefers dark mode')
    expect(chip.getAttribute('title')).toBe('User prefers dark mode')
    // Provenance is claimed only for the fact that was handed in.
    expect(screen.queryByTestId('turn-fact-editor-0')).toBeNull()
  })

  it('draws nothing for an empty or absent memories field', () => {
    const empty = render(<TurnMemories ti={0} memories={[]} reload={vi.fn()} />)
    expect(empty.container.childElementCount).toBe(0)
    empty.unmount()

    const absent = render(<TurnMemories ti={0} memories={undefined} reload={vi.fn()} />)
    expect(absent.container.childElementCount).toBe(0)
  })

  it('opens the inline editor on tap and Retract calls the delete path', async () => {
    const reload = vi.fn()
    render(<TurnMemories ti={0} memories={[FACT]} reload={reload} />)

    fireEvent.click(screen.getByTestId('turn-fact-0-0'))

    const editor = screen.getByTestId('turn-fact-editor-0')
    expect(editor).toBeTruthy()
    expect((screen.getByTestId('turn-fact-input-0') as HTMLTextAreaElement).value).toBe(
      'User prefers dark mode',
    )

    fireEvent.click(screen.getByTestId('turn-fact-retract-0'))

    await waitFor(() => expect(api.deleteMemoryEntry).toHaveBeenCalledWith('m1'))
    // Retract is the delete; the supersede write must stay untouched.
    expect(api.supersedeMemoryEntry).not.toHaveBeenCalled()
    expect(api.updateMemoryEntry).not.toHaveBeenCalled()
    expect(reload).toHaveBeenCalled()
  })
})
