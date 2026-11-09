// The team mode editor offers the iterative orchestration and keeps its cap.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { TeamMode } from './teamEditorFields'
import type { TeamRecord } from '@/lib/api'
import type { T } from './teamShared'

const t = ((key: string) => key) as unknown as T

function draft(overrides: Partial<TeamRecord> = {}): Partial<TeamRecord> {
  return {
    orchestration: 'parallel',
    model_policy: 'inherit',
    model: null,
    budget: { max_rounds: 4, wall_timeout: 300 },
    ...overrides,
  }
}

describe('TeamMode iterative orchestration', () => {
  it('offers iterative as a selectable orchestration', () => {
    const set = vi.fn()
    render(<TeamMode draft={draft()} set={set} t={t} />)
    const select = screen.getByTestId('team-orchestration') as HTMLSelectElement
    const values = Array.from(select.options).map((option) => option.value)
    expect(values).toContain('iterative')
    fireEvent.change(select, { target: { value: 'iterative' } })
    expect(set).toHaveBeenCalledWith({ orchestration: 'iterative' })
  })

  it('shows the iteration cap only for an iterative team', () => {
    const set = vi.fn()
    const { rerender } = render(<TeamMode draft={draft()} set={set} t={t} />)
    expect(screen.queryByTestId('team-max-iterations')).toBeNull()
    rerender(
      <TeamMode
        draft={draft({
          orchestration: 'iterative',
          budget: { max_rounds: 4, wall_timeout: 300, max_iterations: 3 },
        })}
        set={set}
        t={t}
      />,
    )
    expect((screen.getByTestId('team-max-iterations') as HTMLInputElement).value).toBe('3')
  })

  it('keeps the iteration cap when another budget field changes', () => {
    const set = vi.fn()
    render(
      <TeamMode
        draft={draft({
          orchestration: 'iterative',
          budget: { max_rounds: 4, wall_timeout: 300, max_iterations: 3 },
        })}
        set={set}
        t={t}
      />,
    )
    fireEvent.change(screen.getByTestId('team-max-rounds'), { target: { value: '6' } })
    expect(set).toHaveBeenCalledWith({
      budget: { max_rounds: 6, wall_timeout: 300, max_iterations: 3 },
    })
  })

  it('edits the iteration cap without dropping the other budget fields', () => {
    const set = vi.fn()
    render(
      <TeamMode
        draft={draft({
          orchestration: 'iterative',
          budget: { max_rounds: 4, wall_timeout: 300, max_iterations: 3 },
        })}
        set={set}
        t={t}
      />,
    )
    fireEvent.change(screen.getByTestId('team-max-iterations'), { target: { value: '5' } })
    expect(set).toHaveBeenCalledWith({
      budget: { max_rounds: 4, wall_timeout: 300, max_iterations: 5 },
    })
  })
})
