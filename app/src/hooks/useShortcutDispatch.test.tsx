/**
 * P1-16: a surface answers a key because the TABLE names it.
 *
 * The probe below is the real shape of the ChatLayout call: a map of table ids to
 * handlers, mounted once. Every assertion dispatches a genuine KeyboardEvent on the
 * window edge, and the handler receives the table row itself — so a green run means
 * the key was resolved by the table, not by a hand-written `e.key === 'b'` check.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import { useShortcutDispatch, type ShortcutMap } from './useShortcutDispatch'
import { SHORTCUTS_BY_ID } from '@/lib/shortcuts'
import { shortcutListenerCount } from '@/lib/shortcutDispatch'

function Probe({ map }: { map: ShortcutMap }) {
  useShortcutDispatch(map)
  return null
}

const press = (init: KeyboardEventInit) => {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
  act(() => {
    window.dispatchEvent(event)
  })
  return event
}

afterEach(() => {
  cleanup()
})

describe('useShortcutDispatch — one listener, rows from the table', () => {
  it('runs the handler under the row that owns the key', () => {
    const sidebar = vi.fn()
    render(<Probe map={{ sidebar }} />)

    const event = press({ key: 'b', metaKey: true })

    expect(sidebar).toHaveBeenCalledTimes(1)
    // The row identity is the proof: the handler ran because the table named it.
    expect(sidebar).toHaveBeenCalledWith(SHORTCUTS_BY_ID.sidebar, event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('answers ⌘O through the table row that the palette used to own alone', () => {
    const focus = vi.fn()
    render(<Probe map={{ panelFocus: focus }} />)

    press({ key: 'o', metaKey: true })

    expect(focus).toHaveBeenCalledWith(SHORTCUTS_BY_ID.panelFocus, expect.anything())
  })

  it('mounts exactly one window listener', () => {
    expect(shortcutListenerCount()).toBe(0)
    const view = render(<Probe map={{ sidebar: vi.fn() }} />)
    expect(shortcutListenerCount()).toBe(1)
    view.unmount()
    expect(shortcutListenerCount()).toBe(0)
  })

  it('runs a changed callback without re-registering the key', () => {
    const first = vi.fn()
    const second = vi.fn()
    const view = render(<Probe map={{ toggleFiles: first }} />)
    press({ key: 'j', metaKey: true })
    expect(first).toHaveBeenCalledTimes(1)

    act(() => {
      view.rerender(<Probe map={{ toggleFiles: second }} />)
    })
    press({ key: 'j', metaKey: true })

    expect(second).toHaveBeenCalledTimes(1)
    expect(first).toHaveBeenCalledTimes(1)
  })

  it('joins and leaves a second surface without stacking a second listener', () => {
    const a = vi.fn()
    const b = vi.fn()
    const one = render(<Probe map={{ sidebar: a }} />)
    const two = render(<Probe map={{ toggleFiles: b }} />)

    press({ key: 'b', metaKey: true })
    press({ key: 'j', metaKey: true })
    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)

    two.unmount()
    press({ key: 'j', metaKey: true })
    expect(b).toHaveBeenCalledTimes(1)
    press({ key: 'b', metaKey: true })
    expect(a).toHaveBeenCalledTimes(2)

    one.unmount()
  })

  it('stops answering once the surface unmounts', () => {
    const sidebar = vi.fn()
    const view = render(<Probe map={{ sidebar }} />)
    view.unmount()

    const event = press({ key: 'b', metaKey: true })

    expect(sidebar).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('leaves keys the table does not carry to the browser', () => {
    const sidebar = vi.fn()
    render(<Probe map={{ sidebar }} />)

    const event = press({ key: 'q', metaKey: true })

    expect(sidebar).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })
})
