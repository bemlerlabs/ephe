/**
 * Ephe — shared composer-menu shell (P3 wave). Unit contract for the module the
 * three composer menus (plus/model/mode) build on — previously only exercised
 * indirectly through ChatInput.
 *
 * Pinned here, branch by branch:
 *  · useDismissOnOutside — outside mousedown/focusin close, inside does not,
 *    a closed menu listens at all, containment via `el.contains(child)`.
 *  · useMenuFocus — pulls focus into the menu after the rAF commit and hands it
 *    back to the anchor on release().
 *  · useRovingSelection — cyclic move, clamp-to-last on delta 0, zero-count is
 *    a no-op, and both resetKey and count changes reset to 0.
 *  · ComposerMenu — renders null without a measured pos; otherwise a body
 *    portal anchored above the trigger (fixed, -translate-x-1/2), role/aria and
 *    the self/child scroll variants; outside click closes, trigger click not.
 *  · MenuOptionRow — option vs menuitem roles (aria-selected only for option),
 *    aria-current while active, disabled rows swallow the click but stay
 *    visible with their hint, a check mark only when selected.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, renderHook, screen, fireEvent, act } from '@testing-library/react'
import { useRef, useState, type RefObject } from 'react'
import {
  ComposerMenu,
  MenuOptionRow,
  MenuSectionLabel,
  useDismissOnOutside,
  useMenuFocus,
  useRovingSelection,
} from './ComposerMenu'

// useRovingSelection

describe('useRovingSelection — cyclic move with reset', () => {
  it('starts at 0 and moves cyclically forward and back', () => {
    const { result } = renderHook(() => useRovingSelection(3, 'k'))
    expect(result.current.index).toBe(0)
    act(() => result.current.move(1))
    expect(result.current.index).toBe(1)
    act(() => result.current.move(1))
    expect(result.current.index).toBe(2)
    act(() => result.current.move(1)) // last row → first
    expect(result.current.index).toBe(0)
    act(() => result.current.move(-1)) // first row → last
    expect(result.current.index).toBe(2)
  })

  it('delta 0 clamps an out-of-range index to the last row', () => {
    const { result } = renderHook(() => useRovingSelection(3, 'k'))
    act(() => result.current.setIndex(10))
    expect(result.current.index).toBe(2) // the return value already clamps
    act(() => result.current.move(0))
    expect(result.current.index).toBe(2)
    act(() => result.current.setIndex(-5))
    // The return value clamps only the upper end (Math.min); a negative value
    // is pulled to the lower bound (Math.max) only in move().
    expect(result.current.index).toBe(-5)
    act(() => result.current.move(0))
    expect(result.current.index).toBe(0)
  })

  it('an empty list is a no-op (no index, no move)', () => {
    const { result } = renderHook(() => useRovingSelection(0, 'k'))
    expect(result.current.index).toBe(0)
    act(() => result.current.move(1))
    expect(result.current.index).toBe(0)
  })

  it('a resetKey change and a count change reset to 0', () => {
    const { result, rerender } = renderHook(
      ({ count, key }: { count: number; key: string }) => useRovingSelection(count, key),
      { initialProps: { count: 3, key: 'a' } },
    )
    act(() => result.current.move(1))
    expect(result.current.index).toBe(1)
    rerender({ count: 3, key: 'b' })
    expect(result.current.index).toBe(0)

    act(() => result.current.move(1))
    rerender({ count: 2, key: 'b' })
    expect(result.current.index).toBe(0)
  })
})

// useDismissOnOutside

describe('useDismissOnOutside — real outside click instead of a scrim', () => {
  let outside: HTMLDivElement
  let inside: HTMLDivElement

  beforeEach(() => {
    outside = document.createElement('div')
    inside = document.createElement('div')
    document.body.append(outside, inside)
  })
  afterEach(() => {
    outside.remove()
    inside.remove()
  })

  function mountDismiss(open = true) {
    const onClose = vi.fn()
    const { unmount } = renderHook(() => useDismissOnOutside(open, onClose, () => [inside]))
    return { onClose, unmount }
  }

  it('closes on outside mousedown, not inside (including child nodes)', () => {
    const { onClose } = mountDismiss()
    fireEvent.mouseDown(outside)
    expect(onClose).toHaveBeenCalledTimes(1)

    const child = document.createElement('span')
    inside.appendChild(child)
    fireEvent.mouseDown(child)
    expect(onClose).toHaveBeenCalledTimes(1) // contains() also protects children
  })

  it('closes on focus moving outside (Tab), stays open inside', () => {
    const { onClose } = mountDismiss()
    fireEvent.focusIn(outside)
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.focusIn(inside)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('a closed menu does not listen at all', () => {
    const { onClose } = mountDismiss(false)
    fireEvent.mouseDown(outside)
    fireEvent.focusIn(outside)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('null nodes are dead protection, not a crash — a click closes', () => {
    const onClose = vi.fn()
    renderHook(() => useDismissOnOutside(true, onClose, () => [null, undefined]))
    fireEvent.mouseDown(outside)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('unmount removes the listeners', () => {
    const { onClose, unmount } = mountDismiss()
    unmount()
    fireEvent.mouseDown(outside)
    expect(onClose).not.toHaveBeenCalled()
  })
})

// useMenuFocus

describe('useMenuFocus — focus in via rAF, hand back to the anchor', () => {
  const raf = vi.fn()
  const caf = vi.fn()

  beforeEach(() => {
    raf.mockReset()
    caf.mockReset()
    // Synchronous instead of frame-based: the test pins focus semantics, not timing.
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      raf(cb)
      cb(0)
      return 7
    })
    vi.stubGlobal('cancelAnimationFrame', caf)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('focuses the menu ref and release() hands focus back to the anchor', () => {
    const anchor = document.createElement('button')
    document.body.appendChild(anchor)
    const anchorRef = { current: anchor } as RefObject<HTMLElement | null>

    const { result, unmount } = renderHook(() => useMenuFocus(anchorRef))
    const menu = document.createElement('div')
    menu.tabIndex = -1
    document.body.appendChild(menu)
    // Set the ref manually, as after the portal commit.
    ;(result.current.ref as { current: HTMLDivElement | null }).current = menu
    const cb = raf.mock.calls[0]?.[0] as FrameRequestCallback
    cb(0)
    expect(document.activeElement).toBe(menu)

    act(() => result.current.release())
    expect(document.activeElement).toBe(anchor)

    unmount()
    expect(caf).toHaveBeenCalledWith(7)
    anchor.remove()
    menu.remove()
  })
})

// ComposerMenu (Portal)

function MenuHost({
  pos,
  role,
  scroll,
  widthClass,
  withAnchor = true,
}: {
  pos: { left: number; bottom: number } | null
  role?: 'menu' | 'listbox' | null
  scroll?: 'self' | 'child'
  widthClass?: string
  withAnchor?: boolean
}) {
  const anchorRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(true)
  return (
    <>
      {withAnchor && (
        <button ref={anchorRef} data-testid="cm-trigger" onClick={() => setOpen((v) => !v)}>
          chip
        </button>
      )}
      {open && (
        <ComposerMenu
          testId="cm"
          pos={pos}
          anchorRef={anchorRef}
          onClose={() => setOpen(false)}
          role={role}
          ariaLabel="Menu"
          scroll={scroll}
          widthClass={widthClass}
        >
          <div data-testid="cm-body">content</div>
        </ComposerMenu>
      )}
    </>
  )
}

describe('ComposerMenu — portal menu without a scrim', () => {
  it('without a measured position renders nothing (pos = null)', () => {
    render(<MenuHost pos={null} />)
    expect(screen.queryByTestId('cm')).toBeNull()
  })

  it('portals to the body, anchored above with left/bottom from anchorAbove', () => {
    render(<MenuHost pos={{ left: 120, bottom: 64 }} />)
    const menu = screen.getByTestId('cm')
    expect(menu.parentElement).toBe(document.body)
    expect(menu.getAttribute('role')).toBe('menu')
    expect(menu.getAttribute('aria-label')).toBe('Menu')
    expect(menu.style.left).toBe('120px')
    expect(menu.style.bottom).toBe('64px')
    expect(screen.getByTestId('cm-body')).toBeTruthy()
  })

  it('role=null omits the attribute, listbox sets it', () => {
    const { unmount } = render(<MenuHost pos={{ left: 10, bottom: 10 }} role={null} />)
    expect(screen.getByTestId('cm').getAttribute('role')).toBeNull()
    unmount()
    render(<MenuHost pos={{ left: 10, bottom: 10 }} role="listbox" />)
    expect(screen.getByTestId('cm').getAttribute('role')).toBe('listbox')
  })

  it('scroll variants: self scrolls the card, child the content', () => {
    const { unmount } = render(<MenuHost pos={{ left: 10, bottom: 10 }} scroll="child" />)
    const child = screen.getByTestId('cm')
    expect(child.className).toContain('overflow-hidden')
    expect(child.className).toContain('flex flex-col')
    unmount()
    render(<MenuHost pos={{ left: 10, bottom: 10 }} scroll="self" widthClass="min-w-52" />)
    const self = screen.getByTestId('cm')
    expect(self.className).toContain('overflow-y-auto')
    expect(self.className).toContain('min-w-52')
    expect(self.className).toContain('max-h-[min(70vh,30rem)]')
  })

  it('a click beside closes, a click on the trigger does not', () => {
    render(<MenuHost pos={{ left: 10, bottom: 10 }} />)
    // Otherwise the trigger click would be an outside click — the anchor is off-limits.
    fireEvent.mouseDown(screen.getByTestId('cm-trigger'))
    expect(screen.getByTestId('cm')).toBeTruthy()
    fireEvent.mouseDown(screen.getByTestId('cm'))
    expect(screen.getByTestId('cm')).toBeTruthy()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByTestId('cm')).toBeNull()
  })

  it('without a trigger the outside click is still safe (empty anchorRef)', () => {
    render(<MenuHost pos={{ left: 10, bottom: 10 }} withAnchor={false} />)
    fireEvent.mouseDown(document.body)
    expect(screen.queryByTestId('cm')).toBeNull()
  })
})

// MenuSectionLabel + MenuOptionRow

describe('MenuSectionLabel + MenuOptionRow — row contract', () => {
  it('Label renders text and testId', () => {
    render(<MenuSectionLabel testId="sec">Section</MenuSectionLabel>)
    expect(screen.getByTestId('sec').textContent).toBe('Section')
  })

  it('option role: aria-selected follows selected (also false), click selects', () => {
    const onSelect = vi.fn()
    render(
      <MenuOptionRow testId="row" active={false} selected={false} onSelect={onSelect}>
        A
      </MenuOptionRow>,
    )
    const row = screen.getByTestId('row')
    expect(row.getAttribute('role')).toBe('option')
    expect(row.getAttribute('aria-selected')).toBe('false')
    expect(row.getAttribute('tabindex')).toBe('-1')
    expect(screen.queryByText('✓')).toBeNull()
    fireEvent.click(row)
    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  it('menuitem role never carries aria-selected, but ✓ when selected', () => {
    render(
      <MenuOptionRow testId="row" role="menuitem" active={false} selected onSelect={vi.fn()}>
        A
      </MenuOptionRow>,
    )
    const row = screen.getByTestId('row')
    expect(row.getAttribute('role')).toBe('menuitem')
    expect(row.getAttribute('aria-selected')).toBeNull()
    expect(row.textContent).toContain('✓')
  })

  it('active → aria-current, inactive → attribute gone', () => {
    const { unmount } = render(
      <MenuOptionRow testId="row" active onSelect={vi.fn()}>
        A
      </MenuOptionRow>,
    )
    expect(screen.getByTestId('row').getAttribute('aria-current')).toBe('true')
    unmount()
    render(
      <MenuOptionRow testId="row" active={false} onSelect={vi.fn()}>
        A
      </MenuOptionRow>,
    )
    expect(screen.getByTestId('row').getAttribute('aria-current')).toBeNull()
  })

  it('disabled swallows the click, stays visible with aria-disabled and a hint', () => {
    const onSelect = vi.fn()
    render(
      <MenuOptionRow testId="row" active={false} disabled hint="not configured" onSelect={onSelect}>
        A
      </MenuOptionRow>,
    )
    const row = screen.getByTestId('row')
    expect(row.getAttribute('aria-disabled')).toBe('true')
    expect(row.textContent).toContain('not configured')
    fireEvent.click(row)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('hint=null renders no hint, id/title/aria-label pass through', () => {
    render(
      <MenuOptionRow
        id="opt-1"
        testId="row"
        active={false}
        hint={null}
        title="t"
        ariaLabel="Label A"
        onSelect={vi.fn()}
      >
        A
      </MenuOptionRow>,
    )
    const row = screen.getByTestId('row')
    expect(row.id).toBe('opt-1')
    expect(row.getAttribute('title')).toBe('t')
    expect(row.getAttribute('aria-label')).toBe('Label A')
    // No other text node besides the label itself.
    expect(row.textContent?.trim()).toBe('A')
  })
})
