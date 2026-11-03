/**
 * The toast rail and the right column (2026-11-02).
 *
 * Every capture of the panel shows the same defect: the restore toast — "60 messages
 * restored from earlier sessions" — paints straight over the panel's tab bar. The stack
 * anchors top-right, and the panel is a fixed column whose tab bar sits at the very top of
 * the window's right edge, so the two own the same rectangle and the toast is on top
 * (`z-modal` over `z-overlay`). The covered row is the control the reader needs next.
 *
 * The panel already broadcasts its width and dock for the content column's padding. The
 * rail reads that fact and steps to the panel's left edge. jsdom computes no layout, so
 * what is held here is the contract: the clearance arrives with the broadcast, leaves with
 * it, and never reaches for the phone layout's centring.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { PANEL_STATE_EVENT } from '@/lib/panelEvents'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { toastBus } from '@/lib/toast'
import { Toaster } from './Toaster'

function rail(): HTMLElement {
  const close = screen.getByRole('button', { name: 'toast.close' })
  return close.closest('[role="status"]')!.parentElement as HTMLElement
}

function raise() {
  act(() => {
    toastBus.error('Backend getrennt')
  })
}

function broadcast(detail: Record<string, unknown>) {
  act(() => {
    window.dispatchEvent(new CustomEvent(PANEL_STATE_EVENT, { detail }))
  })
}

beforeEach(() => {
  render(<Toaster />)
  raise()
})

describe('the rail beside an open panel', () => {
  it('moves to the panel edge when the column is docked right', () => {
    expect(rail().dataset.cleared).toBe('false')
    broadcast({ open: true, dock: 'right', width: 560, tab: 'files' })
    expect(rail().dataset.cleared).toBe('true')
    expect(rail().style.getPropertyValue('--toast-right')).toBe('576px')
  })

  it('leaves the phone layout alone when the column is docked left', () => {
    broadcast({ open: true, dock: 'left', width: 560, tab: 'files' })
    expect(rail().dataset.cleared).toBe('false')
    expect(rail().style.getPropertyValue('--toast-right')).toBe('1rem')
  })

  it('returns to the corner when the panel closes', () => {
    broadcast({ open: true, dock: 'right', width: 480, tab: 'files' })
    expect(rail().dataset.cleared).toBe('true')
    broadcast({ open: false, dock: 'right', width: 480, tab: 'files' })
    expect(rail().dataset.cleared).toBe('false')
  })

  it('answers for a panel wider than the window', () => {
    // jsdom's innerWidth is 1024; the panel clamps itself to 95vw and the rail must read
    // the same clamp, or a 1400px column would push the stack off the left edge.
    broadcast({ open: true, dock: 'right', width: 1400, tab: 'files' })
    expect(rail().style.getPropertyValue('--toast-right')).toBe(
      `${Math.round(1024 * 0.95) + 16}px`,
    )
  })

  it('keeps the wide-layout anchor on the custom property, so phones stay centred', () => {
    broadcast({ open: true, dock: 'right', width: 560, tab: 'files' })
    const classes = rail().className.split(/\s+/)
    expect(classes).toContain('lg:right-[var(--toast-right)]')
    expect(classes).not.toContain('lg:right-4')
    expect(classes).toContain('max-lg:left-1/2')
    expect(rail().style.right).toBe('')
  })
})
