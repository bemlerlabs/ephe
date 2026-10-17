/**
 * Ephe — composer popups: escape order, @ mention detection, menu positioning
 * (P3 wave 2026-10-05, pure logic without React).
 *
 * P1 of the findings report: the overlay promises «Esc — Panel / Dialog schließen // language-gate: ignore — quoted shortcut-overlay copy, app/src/locales/de.json:1297 close (the shipped text reads «Ephes Computer», not «Panel»)
 * · Generierung stoppen». <!-- language-gate: ignore (quoted shortcut-overlay copy, app/src/locales/de.json:1297) --> So far that is only half kept: while a popup was open,
 * the Escape stop did nothing at all (the plus menu and the @ popup ignored Escape
 * completely). This is the only order the composer knows — top to bottom:
 *
 *   palette / dialog  >  model menu  >  mode menu  >  plus menu  >  @ popup  >  slash list
 *
 * only when nothing is open may Escape stop a generation.
 */

export type ComposerPopupKey = 'model' | 'mode' | 'attach' | 'mention' | 'slash'

export type ComposerPopupState = Record<ComposerPopupKey, boolean>

/** closeTopmostPopup() works this list off from top to bottom. */
export const POPUP_CLOSE_ORDER: ComposerPopupKey[] = ['model', 'mode', 'attach', 'mention', 'slash']

/** Topmost open popup — or null when none is open. */
export function topmostPopup(state: Partial<ComposerPopupState>): ComposerPopupKey | null {
  for (const key of POPUP_CLOSE_ORDER) {
    if (state[key]) return key
  }
  return null
}

/** Roles whose escape behaviour belongs to the opener (palette, dialogs, menus). */
export const OVERLAY_SELECTOR =
  '[role="dialog"],[role="menu"],[role="listbox"],[role="combobox"],[role="tablist"]'

/** Is the element inside an overlay (palette/dialog/menu)? */
export function isInsideOverlay(el: Element | null): boolean {
  return el instanceof Element && Boolean(el.closest(OVERLAY_SELECTOR))
}

/**
 * Is a modal overlay (command palette, dialog) open? It must NOT be touched by the
 * Escape stop — it closes itself, and the composer then neither touches the popups
 * nor stops the generation.
 */
export function hasModalDialog(doc: Document = document): boolean {
  return Boolean(doc.querySelector('[role="dialog"][aria-modal="true"]'))
}

// ── @ mentions ──────────────────────────────────────────────────────────────

export interface MentionToken {
  /** Text from '@' up to the caret (path segments with '/'). */
  query: string
  /** Index of the '@' in the text — the replacement starts there. */
  start: number
}

/**
 * Recognises an @ token at the caret. «@» as the first character counts the same as
 * «@» after text or after a space — the start of the line is a valid word boundary.
 */
export function detectMentionToken(text: string, caret: number): MentionToken | null {
  const before = text.slice(0, Math.max(0, caret))
  const match = before.match(/(^|\s)@([\w.-/]*)$/)
  if (!match) return null
  const query = match[2] ?? ''
  return { query, start: before.length - query.length - 1 }
}

/** «docs/gu» → { dir: 'docs/', segment: 'gu' } — directory + typed section. */
export function mentionPath(query: string): { dir: string; segment: string } {
  const idx = query.lastIndexOf('/')
  if (idx < 0) return { dir: '', segment: query }
  return { dir: query.slice(0, idx + 1), segment: query.slice(idx + 1) }
}

/**
 * Hits for the typed section: prefix hits first, then substring hits, then cut off.
 * Without the filter the list pointlessly showed the plain directory content while
 * the user had already typed (finding P3-3).
 */
export function filterMentionEntries<T extends { name: string }>(
  entries: T[],
  segment: string,
  limit = 8,
): T[] {
  const s = segment.toLowerCase()
  if (!s) return entries.slice(0, limit)
  const prefix: T[] = []
  const contains: T[] = []
  for (const e of entries) {
    const n = e.name.toLowerCase()
    if (n.startsWith(s)) prefix.push(e)
    else if (n.includes(s)) contains.push(e)
  }
  return [...prefix, ...contains].slice(0, limit)
}

// ── Positioning of the upward-opening menus ─────────────────────────────────

export interface MenuPos {
  left: number
  bottom: number
}

/**
 * Anchor above a trigger rectangle (the menu opens upward and is centred via
 * `-translate-x-1/2`). `left` is the centre of the trigger.
 */
export function anchorAbove(
  rect: { left: number; top: number; width: number },
  gap = 6,
  viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 0,
): MenuPos {
  return {
    left: rect.left + rect.width / 2,
    bottom: Math.max(gap, viewportHeight - rect.top + gap),
  }
}

/**
 * Clamp the centre of a centred menu so it sits fully inside the viewport (margin
 * left/right). jsdom reports 0×0 rects — then the centre stays untouched
 * (no NaN, no jumping).
 */
export function clampCenter(
  center: number,
  menuWidth: number,
  viewportWidth: number,
  margin = 8,
): number {
  if (!Number.isFinite(center) || menuWidth <= 0 || viewportWidth <= 0) return center
  const half = menuWidth / 2
  const min = margin + half
  const max = viewportWidth - margin - half
  if (max < min) return Math.round(viewportWidth / 2)
  return Math.round(Math.min(Math.max(center, min), max))
}
