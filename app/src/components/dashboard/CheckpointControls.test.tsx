import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CheckpointControls from './CheckpointControls'
import type { ChatCheckpoint } from '@/lib/checkpoints'

// jsdom returns undefined for window.confirm (falsy) — the destructive
// actions are confirm-gated since the deploy-polish round, so force-accept.
let confirmSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => {
  confirmSpy.mockRestore()
})

function makeCp(label: string): ChatCheckpoint {
  return {
    id: `cp-${label}`,
    label,
    createdAt: Date.now(),
    messages: [],
  }
}

describe('CheckpointControls', () => {
  it('renders the snapshot button', () => {
    render(
      <CheckpointControls
        checkpoints={[]}
        onCreate={vi.fn()}
        onRollback={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByTitle('checkpoints.create')).toBeTruthy()
  })

  it('fires onCreate when the snapshot button is clicked', () => {
    const onCreate = vi.fn()
    render(
      <CheckpointControls
        checkpoints={[]}
        onCreate={onCreate}
        onRollback={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTitle('checkpoints.create'))
    expect(onCreate).toHaveBeenCalled()
  })

  it('lists existing checkpoints', () => {
    render(
      <CheckpointControls
        checkpoints={[makeCp('a'), makeCp('b')]}
        onCreate={vi.fn()}
        onRollback={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    // Rollback buttons share the i18n title; count them instead
    const rollbackBtns = screen.getAllByTitle('checkpoints.rollback')
    expect(rollbackBtns.length).toBe(2)
  })

  it('fires onRollback after confirm', () => {
    const onRollback = vi.fn()
    render(
      <CheckpointControls
        checkpoints={[makeCp('a')]}
        onCreate={vi.fn()}
        onRollback={onRollback}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTitle('checkpoints.rollback'))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onRollback).toHaveBeenCalledWith('cp-a')
  })

  it('does NOT rollback when confirm is dismissed', () => {
    const onRollback = vi.fn()
    confirmSpy.mockReturnValue(false)
    render(
      <CheckpointControls
        checkpoints={[makeCp('a')]}
        onCreate={vi.fn()}
        onRollback={onRollback}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTitle('checkpoints.rollback'))
    expect(onRollback).not.toHaveBeenCalled()
  })

  // Safety default: an empty snapshot is the most destructive rollback there
  // is (it discards every message in the session), so it must never skip the
  // confirmation the way a benign one might.
  it('still asks before rolling back to a checkpoint that holds no messages', () => {
    const onRollback = vi.fn()
    const empty: ChatCheckpoint = {
      id: 'cp-empty',
      label: 'Point 1',
      createdAt: Date.now(),
      messages: [],
    }
    render(
      <CheckpointControls
        checkpoints={[empty]}
        onCreate={vi.fn()}
        onRollback={onRollback}
        onDelete={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTitle('checkpoints.rollback'))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onRollback).toHaveBeenCalledWith('cp-empty')
  })

  it('offers no rollback affordance once the list is empty', () => {
    const { rerender } = render(
      <CheckpointControls
        checkpoints={[makeCp('a')]}
        onCreate={vi.fn()}
        onRollback={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getAllByTitle('checkpoints.rollback')).toHaveLength(1)
    // The store drops the checkpoint; the affordance has to disappear with it,
    // or the row offers a restore to something that no longer exists.
    rerender(
      <CheckpointControls
        checkpoints={[]}
        onCreate={vi.fn()}
        onRollback={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryAllByTitle('checkpoints.rollback')).toHaveLength(0)
  })

  it('fires onDelete after confirm', () => {
    const onDelete = vi.fn()
    render(
      <CheckpointControls
        checkpoints={[makeCp('a')]}
        onCreate={vi.fn()}
        onRollback={vi.fn()}
        onDelete={onDelete}
      />,
    )
    fireEvent.click(screen.getByTitle('checkpoints.delete'))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledWith('cp-a')
  })
})
