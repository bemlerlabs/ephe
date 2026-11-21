/**
 * Ephe — the one shortcut table (P2-4, P1-16 parity audit 2026-10-13).
 *
 * One single source of truth for every keyboard shortcut. Before this the table
 * was display-only: 11 of its 12 ids were referenced nowhere, dispatch was
 * hand-wired by key in ~19 separate `window.addEventListener('keydown')` sites,
 * and ⌘O lived only in the palette's own listener. Now the row *is* the binding:
 *
 *   - the rendered glyph is derived from `binding`, so a glyph cannot drift away
 *     from the key the matcher accepts;
 *   - `matchShortcut` is the one place a KeyboardEvent becomes an id;
 *   - `useShortcutDispatch` installs the one window listener that runs the
 *     handler registered under that id (`@/lib/shortcutDispatch`).
 *
 * `id` is the stable key; nothing else may invent one.
 */

/** The key press a row answers to. `mod` is Cmd on a Mac and Ctrl elsewhere; the
 *  digit family is its own key so ⌘1–⌘0 stays one row instead of ten. */
export interface ShortcutBinding {
  key: string
  mod?: boolean
  shift?: boolean
  alt?: boolean
}

/** How far a key reaches before it is ignored. */
export type ShortcutGuard = 'anywhere' | 'no-typing' | 'no-overlay'

/** `global` rows belong to the one window listener; `field` rows are the
 *  composing surface's own keys (the composer sends on ↵, a dialog closes on Esc)
 *  and must never be dispatched globally. */
export type ShortcutScope = 'global' | 'field'

export type ShortcutGroup = 'navigation' | 'composer' | 'global'

export interface ShortcutDef {
  /** Stable ID — links the declaration (overlay, settings, palette) to the
   *  implementation (the handler registered for it). */
  id: ShortcutId
  /** Rendered glyph, derived from `binding` (Mac form; `renderKeys` swaps it). */
  keys: string
  /** The press this row answers to — the matcher reads this, nothing else. */
  binding: ShortcutBinding
  /** i18n key of the description (sidebar/shortcuts namespace). */
  labelKey: string
  /** Honest fallback (P2-A): the defaultValue for t() while the key is not yet
   *  maintained in de/en.json — the overlay never shows a raw key. */
  fallback?: string
  /** Group for the rows in the keyboard-shortcuts area (I6-5). Pure ordering, no
   *  behaviour — which is why it lives here and not in the backend. */
  group: ShortcutGroup
  guard: ShortcutGuard
  scope: ShortcutScope
}

/** A declarative row. `guard`/`scope` may be omitted for the common case —
 *  reachable anywhere, globally dispatched — so a row carries only what it
 *  actually varies from the default. */
interface Row {
  id: string
  key: string
  mod?: boolean
  shift?: boolean
  alt?: boolean
  labelKey: string
  fallback?: string
  group: ShortcutGroup
  guard?: ShortcutGuard
  scope?: ShortcutScope
}

const ROWS = [
  { id: 'palette', key: 'k', mod: true, labelKey: 'shortcuts.palette', group: 'global' },
  {
    id: 'new',
    key: 'n',
    mod: true,
    labelKey: 'shortcuts.new',
    group: 'navigation',
    guard: 'no-typing',
  },
  { id: 'sidebar', key: 'b', mod: true, labelKey: 'shortcuts.sidebar', group: 'navigation' },
  {
    id: 'panelTabs',
    key: 'digit',
    mod: true,
    labelKey: 'shortcuts.panelTabs',
    group: 'navigation',
    guard: 'no-typing',
  },
  {
    id: 'panelDock',
    key: 'd',
    mod: true,
    shift: true,
    labelKey: 'shortcuts.panelDock',
    group: 'navigation',
  },
  {
    id: 'panelToggle',
    key: 'b',
    mod: true,
    alt: true,
    labelKey: 'shortcuts.panelToggle',
    fallback: 'Toggle panel',
    group: 'navigation',
    guard: 'no-typing',
  },
  // P1-16: ⌘O was handled by the palette listener alone — no row named it, so the
  // help overlay could not tell the user the key existed.
  {
    id: 'panelFocus',
    key: 'o',
    mod: true,
    labelKey: 'shortcuts.panelFocus',
    fallback: 'Focus panel',
    group: 'navigation',
    guard: 'no-typing',
  },
  {
    id: 'focusComposer',
    key: 'f',
    mod: true,
    shift: true,
    labelKey: 'shortcuts.focusComposer',
    group: 'composer',
    guard: 'no-overlay',
  },
  {
    id: 'toggleFiles',
    key: 'j',
    mod: true,
    labelKey: 'shortcuts.toggleFiles',
    group: 'composer',
    guard: 'no-overlay',
  },
  {
    id: 'send',
    key: 'enter',
    labelKey: 'shortcuts.send',
    group: 'composer',
    guard: 'no-overlay',
    scope: 'field',
  },
  { id: 'close', key: 'escape', labelKey: 'shortcuts.close', group: 'global', scope: 'field' },
  {
    id: 'companion',
    key: 'c',
    mod: true,
    shift: true,
    labelKey: 'shortcuts.companion',
    group: 'global',
  },
  {
    id: 'thisOverlay',
    key: '/',
    mod: true,
    labelKey: 'shortcuts.thisOverlay',
    group: 'global',
    guard: 'no-typing',
  },
] as const satisfies readonly Row[]

/** The id union the handlers are typed against — a typo in a registration is a
 *  compile error, not a key that silently does nothing. */
export type ShortcutId = (typeof ROWS)[number]['id']

/** Mac glyph for one row. The one place a glyph is written; `renderKeys` swaps it
 *  for the Ctrl form off a Mac. */
function glyph(b: ShortcutBinding): string {
  const parts: string[] = []
  if (b.mod) parts.push('⌘')
  if (b.shift) parts.push('⇧')
  if (b.alt) parts.push('⌥')
  if (b.key === 'digit') parts.push('1–0')
  else if (b.key === 'enter') parts.push('↵')
  else if (b.key === 'escape') parts.push('Esc')
  else parts.push(b.key.toUpperCase())
  return parts.join(' ')
}

/** Mac glyph or the Ctrl variant — the same question in two places (overlay,
 *  settings area), so it is answered once. */
export function isMacPlatform(): boolean {
  if (typeof navigator === 'undefined') return false
  return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
}

function toDef(r: Row): ShortcutDef {
  const binding: ShortcutBinding = { key: r.key, mod: r.mod, shift: r.shift, alt: r.alt }
  return {
    // The union is read off this list, so the row's own id is one of its members.
    id: r.id as ShortcutId,
    binding,
    keys: glyph(binding),
    labelKey: r.labelKey,
    fallback: r.fallback,
    group: r.group,
    // Omitted in the row means the common case: reachable anywhere, dispatched
    // globally (the defaults the expanded table carried explicitly before).
    guard: r.guard ?? 'anywhere',
    scope: r.scope ?? 'global',
  }
}

export const SHORTCUTS: readonly ShortcutDef[] = ROWS.map(toDef)

export const SHORTCUTS_BY_ID = Object.fromEntries(SHORTCUTS.map((s) => [s.id, s])) as Record<
  ShortcutId,
  ShortcutDef
>

/** The glyph one row displays, ready to render (Mac or Ctrl form). Every surface
 *  that shows a key — palette, overlay, settings — shows this string. */
export function shortcutGlyph(id: ShortcutId, isMac: boolean = isMacPlatform()): string {
  return renderKeys(SHORTCUTS_BY_ID[id].keys, isMac)
}

/** The shape `matchShortcut` reads — a DOM KeyboardEvent satisfies it as-is, and a
 *  test can hand in a plain object. */
export interface KeyLike {
  key: string
  metaKey?: boolean
  ctrlKey?: boolean
  shiftKey?: boolean
  altKey?: boolean
}

/** P1-16: the one key-to-row resolution. Exact modifier match, so ⌘F (native find)
 *  can never be answered by the ⌘⇧F row; `mod` accepts Ctrl where the Mac form is
 *  Cmd. Returns null for every key the table does not carry. */
export function matchShortcut(e: KeyLike): ShortcutDef | null {
  const mod = !!e.metaKey || !!e.ctrlKey
  const key = e.key.toLowerCase()
  for (const s of SHORTCUTS) {
    const b = s.binding
    if (mod !== !!b.mod) continue
    if (!!e.shiftKey !== !!b.shift) continue
    if (!!e.altKey !== !!b.alt) continue
    if (b.key === 'digit') {
      if (/^[0-9]$/.test(key)) return s
      continue
    }
    if (key === b.key) return s
  }
  return null
}

/** Swap Mac glyphs for the non-Mac labels (⌘ → Ctrl). */
export function renderKeys(keys: string, isMac: boolean): string {
  if (isMac) return keys
  return keys
    .replace(/⌘/g, 'Ctrl')
    .replace(/⇧/g, 'Shift')
    .replace(/⌥/g, 'Alt')
    .replace(/↵/g, 'Enter')
}
