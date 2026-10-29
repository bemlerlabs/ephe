import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SolHeuristicsCard } from './SolHeuristicsCard'

// SOL: the inspector is a view on `.ephe/learning/heuristics.md` — it lists what
// is stored, edits one action and deletes one rule, each through the API.

const rule = {
  id: 'H1',
  title: 'The project tools are not on the shell PATH',
  kind: 'command-not-found',
  trigger: 'A tool call fails with command-not-found',
  insight: '`node` resolves to /opt/homebrew/bin/node',
  action: 'Prepend /opt/homebrew/bin to PATH',
  verified_at: '2026-10-29T14:00:00Z',
}

vi.mock('@/lib/api/endpoints', () => ({
  getSolHeuristics: vi.fn(),
  updateSolHeuristic: vi.fn(),
  deleteSolHeuristic: vi.fn(),
}))

import { deleteSolHeuristic, getSolHeuristics, updateSolHeuristic } from '@/lib/api/endpoints'

const t = (key: string) => {
  const map: Record<string, string> = {
    'settings.solGroup': 'Learned project rules',
    'settings.solEmpty': 'No rule learned yet',
    'settings.solEmptyHint': 'A rule is stored once a correction ends a failed round.',
    'settings.solEdit': 'Edit rule',
    'settings.solEditHint': 'This action is what Ephe applies next time.',
    'settings.solActionLabel': 'Rule action',
    'settings.solSave': 'Save',
    'settings.cancel': 'Cancel',
    'settings.solDelete': 'Delete rule',
    'settings.solDeleteConfirm': 'Confirm delete',
  }
  return map[key] ?? key
}

function view(heuristics: (typeof rule)[]) {
  return { workspace: '/tmp/demo', enabled: true, max_active: 15, heuristics, map: null }
}

describe('SolHeuristicsCard', () => {
  beforeEach(() => {
    vi.mocked(getSolHeuristics).mockReset()
    vi.mocked(updateSolHeuristic).mockReset()
    vi.mocked(deleteSolHeuristic).mockReset()
  })

  it('says so when the store holds no rule', async () => {
    vi.mocked(getSolHeuristics).mockResolvedValue(view([]) as never)
    render(<SolHeuristicsCard t={t} />)
    await waitFor(() => expect(screen.getByTestId('sol-empty')).toBeTruthy())
    expect(screen.getByText('No rule learned yet')).toBeTruthy()
  })

  it('lists the stored rules with the action Ephe applies', async () => {
    vi.mocked(getSolHeuristics).mockResolvedValue(view([rule]) as never)
    render(<SolHeuristicsCard t={t} />)
    await waitFor(() => expect(screen.getByTestId('sol-rule-H1')).toBeTruthy())
    expect(screen.getByText(rule.title)).toBeTruthy()
    expect(screen.getByText(rule.action)).toBeTruthy()
  })

  it('edits one action and shows the stored answer', async () => {
    vi.mocked(getSolHeuristics).mockResolvedValue(view([rule]) as never)
    vi.mocked(updateSolHeuristic).mockResolvedValue({
      heuristic: { ...rule, action: 'Call /opt/homebrew/bin/node directly' },
    } as never)
    render(<SolHeuristicsCard t={t} />)
    await waitFor(() => expect(screen.getByTestId('sol-edit-H1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('sol-edit-H1'))
    fireEvent.change(screen.getByTestId('sol-draft-H1'), {
      target: { value: 'Call /opt/homebrew/bin/node directly' },
    })
    fireEvent.click(screen.getByTestId('sol-save-H1'))
    await waitFor(() => expect(updateSolHeuristic).toHaveBeenCalledWith('H1', { action: 'Call /opt/homebrew/bin/node directly' }))
    await waitFor(() => expect(screen.getByText('Call /opt/homebrew/bin/node directly')).toBeTruthy())
  })

  it('deletes a rule only after the second click', async () => {
    vi.mocked(getSolHeuristics).mockResolvedValue(view([rule]) as never)
    vi.mocked(deleteSolHeuristic).mockResolvedValue({ status: 'deleted', id: 'H1' } as never)
    render(<SolHeuristicsCard t={t} />)
    await waitFor(() => expect(screen.getByTestId('sol-delete-H1')).toBeTruthy())
    fireEvent.click(screen.getByTestId('sol-delete-H1'))
    expect(deleteSolHeuristic).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('sol-delete-H1'))
    await waitFor(() => expect(deleteSolHeuristic).toHaveBeenCalledWith('H1'))
    await waitFor(() => expect(screen.getByTestId('sol-empty')).toBeTruthy())
  })
})
