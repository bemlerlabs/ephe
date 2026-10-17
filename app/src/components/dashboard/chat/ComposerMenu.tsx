/**
 * Ephe — shared shell for the composer menus (P3 wave 2026-10-05).
 *
 * Why its own module: ChatInput.tsx is far above the architecture limit, and the
 * menu shell was repeated three times almost identically. Plus the two findings
 * from the user's review run:
 *
 *  · The plus menu sat with `absolute` inside the composer panel — the first two
 *    entries («Datei anhängen», «Bild anhängen») were painted over by the composer // language-gate: ignore — both are German labels the UI renders (de.json:85-86)
 *    window (measured: the rows' hit test returns `composer-actions-row`).
 *    → every composer menu is portalled to body, anchored above the trigger and
 *    clamped horizontally to the viewport.
 *  · Above the window sat `div.fixed.inset-0.z-overlay`: the sidebar was dead to
 *    clicks, the first click only went to closing it — even the text field itself
 *    was no longer reachable.
 *    → NO scrim anymore; closing runs on real outside-click/focus listeners that
 *    leave the window alone.
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react'
import { createPortal } from 'react-dom'
import { clampCenter, type MenuPos } from './composerPopups'

export type { MenuPos } from './composerPopups'

/**
 * Closes a popup on click/focus outside it — without a full-screen overlay.
 * `getNodes` returns the protected nodes (menu + trigger).
 *
 * Listening happens on pointerdown (touch/mouse) AND mousedown: test environments
 * (jsdom) have no pointer events, so there the mousedown path is what lands.
 */
export function useDismissOnOutside(
  open: boolean,
  onClose: () => void,
  getNodes: () => (HTMLElement | null | undefined)[],
) {
  const nodesRef = useRef(getNodes)
  nodesRef.current = getNodes
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    if (!open) return
    const closeNow = () => closeRef.current()
    const inside = (target: EventTarget | null) => {
      if (!(target instanceof Node)) return false
      return nodesRef.current().some((el) => Boolean(el && (el === target || el.contains(target))))
    }
    const onDown = (e: Event) => {
      if (!inside(e.target)) closeNow()
    }
    const onFocusIn = (e: Event) => {
      // Tab stop outside: the menu goes away, focus stays where it is.
      if (!inside(e.target)) closeNow()
    }
    document.addEventListener('pointerdown', onDown, true)
    document.addEventListener('mousedown', onDown, true)
    document.addEventListener('focusin', onFocusIn)
    return () => {
      document.removeEventListener('pointerdown', onDown, true)
      document.removeEventListener('mousedown', onDown, true)
      document.removeEventListener('focusin', onFocusIn)
    }
  }, [open])
}

/**
 * Pull focus into an open menu (keyboard operation) and hand it back to the
 * trigger when the menu closes by keyboard. An outside click deliberately does
 * NOT call `release` — focus stays where the user clicked.
 */
export function useMenuFocus(anchorRef: RefObject<HTMLElement | null>) {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    // requestAnimationFrame: in the test renderer the portal node is only in the
    // document after this commit.
    const id = requestAnimationFrame(() => ref.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [])
  const release = useCallback(() => {
    anchorRef.current?.focus()
  }, [anchorRef])
  return { ref, release }
}

/** Roving highlight: index 0 = first row; resets when the list changes. */
export function useRovingSelection(count: number, resetKey: unknown) {
  const [index, setIndex] = useState(0)
  useEffect(() => {
    setIndex(0)
  }, [resetKey, count])
  /** delta ≠ 0 → cyclic; `clamp` keeps the index on the last row. */
  const move = (delta: number) => {
    if (count <= 0) return
    setIndex((i) => {
      const base = Math.min(Math.max(i, 0), count - 1)
      return delta === 0 ? base : (base + delta + count) % count
    })
  }
  return { index: count > 0 ? Math.min(index, count - 1) : 0, setIndex, move }
}

export interface ComposerMenuProps {
  testId: string
  /** Anchor from `anchorAbove()` — null until the trigger rect is measured. */
  pos: MenuPos | null
  /** Trigger (chip/button) — a click on it does NOT close via the outside-listener. */
  anchorRef: RefObject<HTMLElement | null>
  onClose: () => void
  /** null = no role (the content brings its own roles, e.g. listbox). */
  role?: 'menu' | 'listbox' | null
  ariaLabel?: string
  /** Width class of the container (min-w-…), so the menu does not collapse. */
  widthClass?: string
  /** 'self' = the container scrolls itself, 'child' = a child element scrolls. */
  scroll?: 'self' | 'child'
  children: ReactNode
}

/**
 * Composer menu opening upwards as a body portal: maximum height against the
 * viewport, internal scroll list, pulled back horizontally into the viewport.
 */
export function ComposerMenu({
  testId,
  pos,
  anchorRef,
  onClose,
  role = 'menu',
  ariaLabel,
  widthClass = 'min-w-44',
  scroll = 'self',
  children,
}: ComposerMenuProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [left, setLeft] = useState<number>(pos?.left ?? 0)
  const anchorCenter = pos?.left ?? 0
  const anchorBottom = pos?.bottom ?? 0

  useEffect(() => {
    setLeft(anchorCenter)
  }, [anchorCenter])

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const w = el.offsetWidth
    // jsdom measures 0 — then the anchor centre stays put (no flickering).
    if (!w || !anchorCenter) return
    const next = clampCenter(anchorCenter, w, window.innerWidth)
    if (next !== left) setLeft(next)
  }, [anchorCenter, anchorBottom, left, children])

  useDismissOnOutside(true, onClose, () => [ref.current, anchorRef.current])

  if (!pos) return null
  return createPortal(
    <div
      ref={ref}
      data-testid={testId}
      role={role ?? undefined}
      aria-label={ariaLabel}
      style={{ left, bottom: anchorBottom }}
      className={`fixed -translate-x-1/2 z-modal rounded-xl border border-hairline bg-surface shadow-elevation-2 max-h-[min(70vh,30rem)] ${widthClass} ${
        scroll === 'self'
          ? 'overflow-y-auto overscroll-contain py-1.5'
          : 'overflow-hidden flex flex-col'
      }`}
    >
      {children}
    </div>,
    document.body,
  )
}

/** Section header inside a menu (no selection, only reading direction). */
export function MenuSectionLabel({ testId, children }: { testId?: string; children: ReactNode }) {
  return (
    <p
      data-testid={testId}
      className="px-3 pt-2 pb-1 text-ui-2xs uppercase tracking-wide text-ink-faint select-none"
    >
      {children}
    </p>
  )
}

export interface MenuOptionProps {
  id?: string
  testId: string
  active: boolean
  selected?: boolean
  disabled?: boolean
  title?: string
  ariaLabel?: string
  hint?: ReactNode
  onSelect: () => void
  children: ReactNode
  /**
   * Role mapping of the row: 'option' (listbox), 'menuitem' (action menu) or
   * 'menuitemradio' (single-choice menu). Only the radio role carries
   * `aria-checked`, so assistive tech reads which entry is the active one.
   */
  role?: 'option' | 'menuitem' | 'menuitemradio'
}

/**
 * One row: keyboard marking via aria-selected/aria-current, disabled via
 * aria-disabled (never click-dead without a reason — the reason stands there as a hint).
 */
export function MenuOptionRow({
  id,
  testId,
  active,
  selected = false,
  disabled = false,
  title,
  ariaLabel,
  hint,
  onSelect,
  children,
  role = 'option',
}: MenuOptionProps) {
  // Below lg the row reaches the 44px touch floor: at the desktop ~28px the plus,
  // mode and model rows were hard to hit on a phone. The class is what jsdom can
  // hold; the pixel proof is the playwright lane.
  return (
    <button
      id={id}
      type="button"
      role={role}
      data-testid={testId}
      aria-selected={role === 'option' ? selected : undefined}
      aria-checked={role === 'menuitemradio' ? selected : undefined}
      aria-current={active ? 'true' : undefined}
      aria-disabled={disabled || undefined}
      tabIndex={-1}
      title={title}
      aria-label={ariaLabel}
      onClick={() => {
        if (!disabled) onSelect()
      }}
      className={`w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 transition-colors min-w-0 max-lg:min-h-11 ${
        disabled
          ? 'text-ink-faint/70 cursor-default'
          : active
            ? 'bg-brand/20 text-foreground'
            : 'text-ink-faint hover:bg-brand/10 hover:text-foreground'
      }`}
    >
      <span className="truncate min-w-0">{children}</span>
      {hint != null && <span className="shrink-0 text-ui-2xs text-ink-faint">{hint}</span>}
      {selected && (
        <span className="ml-auto shrink-0 text-ui-xs text-brand" aria-hidden="true">
          ✓
        </span>
      )}
    </button>
  )
}
