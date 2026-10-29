/**
 * The pet stays where the hand puts it.
 *
 * A drag is not a click: the panel must not open after the figure was moved,
 * the offset has to survive a reload, and a pet parked at an edge of a wide
 * window has to stay reachable in a narrow one.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { clampOffset, offsetBounds, useCompanionDrag } from './useCompanionDrag'

function Pet({ onActivate }: { onActivate?: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const drag = useCompanionDrag(
    box,
    (target) => target instanceof Element && target.closest('[data-testid="companion-trigger"]') !== null,
  )
  return (
    <div ref={box} style={drag.style} {...drag.handlers} data-testid="pet" data-dragging={drag.dragging ? 'true' : undefined}>
      <button type="button" data-testid="companion-trigger" onClick={onActivate}>
        moth
      </button>
    </div>
  )
}

function drag(start: [number, number], end: [number, number]) {
  const trigger = screen.getByTestId('companion-trigger')
  fireEvent.pointerDown(trigger, { pointerId: 1, button: 0, clientX: start[0], clientY: start[1] })
  fireEvent.pointerMove(trigger, { pointerId: 1, clientX: end[0], clientY: end[1] })
  fireEvent.pointerUp(trigger, { pointerId: 1, clientX: end[0], clientY: end[1] })
}

describe('useCompanionDrag', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('keeps the figure inside the viewport at every edge', () => {
    const bounds = offsetBounds(
      { left: 900, top: 600, width: 80, height: 80 },
      { left: 0, top: 0, width: 1000, height: 800 },
    )
    expect(clampOffset({ x: 500, y: 500 }, bounds)).toEqual({ x: 12, y: 112 })
    expect(clampOffset({ x: -5000, y: -5000 }, bounds)).toEqual({ x: -892, y: -592 })
  })

  it('moves the box on a pointer drag and marks it as dragging', () => {
    render(<Pet />)
    drag([0, 0], [60, 40])
    expect(screen.getByTestId('pet').style.translate).toContain('60.0px')
    expect(screen.getByTestId('pet').style.translate).toContain('40.0px')
  })

  it('a drag does not open the panel it was moving', () => {
    const onActivate = vi.fn()
    render(<Pet onActivate={onActivate} />)
    drag([0, 0], [40, 30])
    fireEvent.click(screen.getByTestId('companion-trigger'))
    expect(onActivate).not.toHaveBeenCalled()
  })

  it('a press that stays put is still a click', () => {
    const onActivate = vi.fn()
    render(<Pet onActivate={onActivate} />)
    const trigger = screen.getByTestId('companion-trigger')
    fireEvent.pointerDown(trigger, { pointerId: 1, button: 0, clientX: 10, clientY: 10 })
    fireEvent.pointerUp(trigger, { pointerId: 1, clientX: 10, clientY: 10 })
    fireEvent.click(trigger)
    expect(onActivate).toHaveBeenCalledTimes(1)
  })

  it('remembers the offset as a fraction of the viewport', () => {
    const first = render(<Pet />)
    drag([0, 0], [100, 50])
    const parked = screen.getByTestId('pet').style.translate
    expect(window.localStorage.getItem('ephe.companion.offset.v1')).toBeTruthy()
    first.unmount()
    render(<Pet />)
    expect(screen.getByTestId('pet').style.translate).toBe(parked)
  })

  it('a double click brings the pet home and forgets the offset', () => {
    render(<Pet />)
    drag([0, 0], [80, 40])
    fireEvent.doubleClick(screen.getByTestId('companion-trigger'))
    expect(screen.getByTestId('pet').style.translate).toBe('')
    expect(window.localStorage.getItem('ephe.companion.offset.v1')).toBeNull()
  })

  it('a press on a control inside the box never starts a drag', () => {
    render(<Pet />)
    const box = screen.getByTestId('pet')
    fireEvent.pointerDown(box, { pointerId: 1, button: 0, clientX: 0, clientY: 0 })
    fireEvent.pointerMove(box, { pointerId: 1, clientX: 90, clientY: 90 })
    fireEvent.pointerUp(box, { pointerId: 1, clientX: 90, clientY: 90 })
    expect(box.style.translate).toBe('')
  })
})
