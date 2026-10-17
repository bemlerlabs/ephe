/**
 * Ephe — the one shortcut dispatcher (P1-16 parity audit 2026-10-13).
 *
 * Before this every surface wired its own `window.addEventListener('keydown')`
 * and compared keys by hand in ~19 places — the table could name a key nobody
 * handled, and two listeners answered ⌘N at once. Here the keydown becomes a
 * table row (`matchShortcut`) and that row's id picks the handler. One listener,
 * one resolution, one place a key can be answered.
 */
import { matchShortcut, type ShortcutDef, type ShortcutGuard, type ShortcutId } from './shortcuts'

export type ShortcutHandler = (def: ShortcutDef, event: KeyboardEvent) => void

const handlers = new Map<string, Set<ShortcutHandler>>()

/** Attaches a handler to a table row. The returned function detaches it — call it
 *  from an effect cleanup, so a re-render cannot stack two handlers on one key. */
export function registerShortcut(id: ShortcutId, handler: ShortcutHandler): () => void {
  let set = handlers.get(id)
  if (!set) {
    set = new Set()
    handlers.set(id, set)
  }
  set.add(handler)
  return () => {
    set.delete(handler)
    if (set.size === 0) handlers.delete(id)
  }
}

/** Which rows currently have a handler — the honest half of "the overlay does not
 *  lie", used by the tests and available for a future debug surface. */
export function registeredShortcutIds(): string[] {
  return [...handlers.keys()]
}

/** Shared focus rule: `no-typing` is ignored while a text field has focus,
 *  `no-overlay` also while a dialog/menu/listbox/tablist does. */
export function guardBlocks(guard: ShortcutGuard): boolean {
  if (guard === 'anywhere') return false
  const el = typeof document === 'undefined' ? null : document.activeElement
  if (!(el instanceof HTMLElement)) return false
  const typing =
    el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable === true
  if (guard === 'no-typing') return typing
  return (
    typing ||
    Boolean(el.closest('[role="dialog"], [role="menu"], [role="listbox"], [role="tablist"]'))
  )
}

/**
 * The one resolution: a keydown becomes a table row, the row's id becomes the
 * handler. Returns the row that ran, or null when the key is not in the table,
 * the row is field-local (the composer owns ↵, a dialog owns Esc), the guard
 * blocks it, or nobody registered for that id.
 */
export function dispatchShortcut(event: KeyboardEvent): ShortcutDef | null {
  const def = matchShortcut(event)
  if (!def || def.scope !== 'global') return null
  if (guardBlocks(def.guard)) return null
  const set = handlers.get(def.id)
  if (!set || set.size === 0) return null
  event.preventDefault()
  for (const handler of [...set]) handler(def, event)
  return def
}

function onKeydown(event: KeyboardEvent): void {
  dispatchShortcut(event)
}

let listeners = 0

/**
 * Installs THE window keydown listener and returns the release. Ref-counted, so
 * every caller can mount one and the page still carries exactly one listener
 * (two listeners on one key was the defect, not the fix).
 */
export function installShortcutListener(): () => void {
  if (typeof window === 'undefined') return () => {}
  if (listeners === 0) window.addEventListener('keydown', onKeydown)
  listeners += 1
  let released = false
  return () => {
    if (released) return
    released = true
    listeners -= 1
    if (listeners === 0) window.removeEventListener('keydown', onKeydown)
  }
}

/** Test seam: how many window listeners are attached (must never exceed one). */
export function shortcutListenerCount(): number {
  return listeners
}
