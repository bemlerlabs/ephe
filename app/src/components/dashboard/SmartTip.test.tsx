import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import SmartTip from '@/components/dashboard/SmartTip'

// H round H1 (2026-09-07, reference parity): reference-B-style hover popups —
// Hovering an element shows a small explainer popup (title +
// line). Keyboard focus shows it as well (a11y), touch (no hover) never.

describe('SmartTip (H1, reference parity)', () => {
  it('shows title and explanation after the hover delay and hides them on blur', async () => {
    vi.useFakeTimers()
    render(
      <SmartTip tip={{ title: 'Review-Tab', body: 'Zeigt die Aenderungen deiner Arbeitskopie.' }}>
        <button>Trigger</button>
      </SmartTip>,
    )
    expect(screen.queryByText('Review-Tab')).toBeNull()
    fireEvent.mouseEnter(screen.getByText('Trigger'))
    // The delay guards against hover noise (reference-B pattern ~350ms)
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(screen.queryByText('Review-Tab')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(screen.getByText('Review-Tab')).toBeTruthy()
    expect(screen.getByText('Zeigt die Aenderungen deiner Arbeitskopie.')).toBeTruthy()
    fireEvent.mouseLeave(screen.getByText('Trigger'))
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(screen.queryByText('Review-Tab')).toBeNull()
    vi.useRealTimers()
  })

  it('focus shows the tip at once (keyboard path, no delay)', () => {
    render(
      <SmartTip tip={{ title: 'M', body: 'Geaenderte Datei.' }}>
        <button>Chip</button>
      </SmartTip>,
    )
    fireEvent.focus(screen.getByText('Chip'))
    expect(screen.getByText('M')).toBeTruthy()
    fireEvent.blur(screen.getByText('Chip'))
    expect(screen.queryByText('M')).toBeNull()
  })

  it('the popup renders as a portaled fixed element, clip-immune, below the trigger', () => {
    render(
      <SmartTip tip={{ title: 'T', body: 'B' }} side="bottom">
        <button>X</button>
      </SmartTip>,
    )
    fireEvent.focus(screen.getByText('X'))
    const popup = screen.getByText('T').closest('[data-testid="smart-tip-popup"]') as HTMLElement
    expect(popup.style.position).toBe('fixed')
    // bottom-side: top is set (below the trigger), no bottom anchor
    expect(popup.style.top).not.toBe('')
    expect(popup.style.bottom).toBe('')
    expect(popup.getAttribute('role')).toBe('tooltip')
    expect(document.body.contains(popup)).toBe(true)
  })

  it('the block variant wraps full-width elements without hiding them on touch', () => {
    const { container } = render(
      <SmartTip block tip={{ title: 'Karte', body: 'Erklaerung.' }}>
        <div data-testid="card-inner">Karte</div>
      </SmartTip>,
    )
    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.className).toContain('block')
    expect(wrapper.className).not.toContain('hidden')
  })
})
