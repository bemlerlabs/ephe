/**
 * P1-16: the dispatcher runs a handler because the TABLE names the key.
 *
 * Every test here dispatches a real KeyboardEvent on the window edge — no direct
 * calls into the registry — so a green run means the key reached the table and the
 * table reached the handler.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { SHORTCUTS, SHORTCUTS_BY_ID } from './shortcuts'
import {
  dispatchShortcut,
  installShortcutListener,
  registerShortcut,
  shortcutListenerCount,
  type ShortcutHandler,
} from './shortcutDispatch'

let release: () => void
let offs: Array<() => void>

/** Register a handler and queue its detach for afterEach. */
function on(id: Parameters<typeof registerShortcut>[0], handler: ShortcutHandler) {
  offs.push(registerShortcut(id, handler))
}

const press = (init: KeyboardEventInit) => {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
  window.dispatchEvent(event)
  return event
}

beforeEach(() => {
  offs = []
  release = installShortcutListener()
})

afterEach(() => {
  offs.forEach((off) => off())
  release()
})

describe('dispatchShortcut — window keydown → table row → its handler', () => {
  it('runs the handler registered for the row the table names', () => {
    const ran = vi.fn()
    on('sidebar', ran)

    const event = press({ key: 'b', metaKey: true })

    expect(ran).toHaveBeenCalledTimes(1)
    // The handler is handed the TABLE row — identity, not a copy of the key.
    expect(ran).toHaveBeenCalledWith(SHORTCUTS_BY_ID.sidebar, event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('answers the row’s own id and not a neighbour that shares the letter', () => {
    const sidebar = vi.fn()
    const panelToggle = vi.fn()
    on('sidebar', sidebar)
    on('panelToggle', panelToggle)

    press({ key: 'b', metaKey: true })
    expect(sidebar).toHaveBeenCalledTimes(1)
    expect(panelToggle).not.toHaveBeenCalled()

    press({ key: 'b', metaKey: true, altKey: true })
    expect(panelToggle).toHaveBeenCalledTimes(1)
    expect(sidebar).toHaveBeenCalledTimes(1)
  })

  it('drives every global row from its own declaration', () => {
    // The sweep that makes the table binding: register one handler per global row,
    // press each row's binding, and only that row's handler may fire.
    const fired: string[] = []
    for (const s of SHORTCUTS.filter((x) => x.scope === 'global')) {
      on(s.id, () => fired.push(s.id))
    }

    for (const s of SHORTCUTS.filter((x) => x.scope === 'global')) {
      fired.length = 0
      press({
        key: s.binding.key === 'digit' ? '4' : s.binding.key,
        metaKey: s.binding.mod,
        shiftKey: s.binding.shift,
        altKey: s.binding.alt,
      })
      expect(fired, `${s.id} must be driven by its own binding`).toEqual([s.id])
    }
  })

  it('names a row for ⌘O that the table, not the palette, owns', () => {
    const focus = vi.fn()
    on('panelFocus', focus)

    press({ key: 'o', metaKey: true })

    expect(focus).toHaveBeenCalledWith(SHORTCUTS_BY_ID.panelFocus, expect.anything())
  })

  it('leaves the composing keys to the surface that has focus', () => {
    const send = vi.fn()
    const close = vi.fn()
    on('send', send)
    on('close', close)

    const enter = press({ key: 'Enter' })
    const escape = press({ key: 'Escape' })

    expect(send).not.toHaveBeenCalled()
    expect(close).not.toHaveBeenCalled()
    expect(enter.defaultPrevented).toBe(false)
    expect(escape.defaultPrevented).toBe(false)
    expect(dispatchShortcut(enter)).toBeNull()
  })

  it('ignores a table row nobody registered for — and does not swallow the key', () => {
    const event = press({ key: 'j', metaKey: true })
    expect(event.defaultPrevented).toBe(false)
    expect(dispatchShortcut(event)).toBeNull()
  })

  it('ignores keys the table does not carry at all', () => {
    const event = press({ key: 'q', metaKey: true })
    expect(event.defaultPrevented).toBe(false)
    expect(dispatchShortcut(event)).toBeNull()
  })

  it('stops answering once the handler is detached', () => {
    const ran = vi.fn()
    const off = registerShortcut('toggleFiles', ran)
    press({ key: 'j', metaKey: true })
    expect(ran).toHaveBeenCalledTimes(1)

    off()
    press({ key: 'j', metaKey: true })
    expect(ran).toHaveBeenCalledTimes(1)
  })

  it('honours the focus guard the row declares', () => {
    const sidebar = vi.fn() // guard: anywhere — the sidebar key still works while typing
    const files = vi.fn() // guard: no-overlay
    on('sidebar', sidebar)
    on('toggleFiles', files)

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    try {
      press({ key: 'j', metaKey: true })
      press({ key: 'b', metaKey: true })
    } finally {
      input.remove()
    }

    expect(files).not.toHaveBeenCalled()
    expect(sidebar).toHaveBeenCalledTimes(1)
  })

  it('installs exactly one window listener however often it is mounted', () => {
    // Three mounts (the real app mounts the dispatcher once; a hot reload mounts
    // again) must still produce one handler run per key — the old defect was two
    // listeners answering ⌘N and creating two sessions.
    const extra = [installShortcutListener(), installShortcutListener()]
    const ran = vi.fn()
    on('sidebar', ran)

    press({ key: 'b', metaKey: true })

    expect(shortcutListenerCount()).toBe(3)
    expect(ran).toHaveBeenCalledTimes(1)
    extra.forEach((off) => off())
  })
})
