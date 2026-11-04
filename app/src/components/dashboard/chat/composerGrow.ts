import { useEffect, useLayoutEffect, type RefObject } from 'react'

/**
 * EPHE-UI-001 (P0) — the composer's auto-grow rule, in lines of the input ramp.
 *
 * The ramp is `--text-ui-input--line-height` (20px), and the composer's own
 * breathing room is `py-1` (4px top and bottom). Those two numbers decide
 * everything else, so they live here rather than as loose pixels in the class
 * list: one line is the floor a person stares at, six lines is the cap, and past
 * the cap the field scrolls internally so a multi-line prompt stays readable
 * while it is edited. `max-h-32` on the element is the same 128px from the CSS
 * side — the class carries it, this module agrees with it.
 */
export const COMPOSER_LINE_PX = 20
export const COMPOSER_PADDING_PX = 8
export const COMPOSER_MAX_LINES = 6
/** One line plus the field's padding: the height of an empty composer. */
export const COMPOSER_EMPTY_PX = COMPOSER_LINE_PX + COMPOSER_PADDING_PX
/** Six lines plus the same padding — the tallest the composer may take. */
export const COMPOSER_MAX_PX = COMPOSER_LINE_PX * COMPOSER_MAX_LINES + COMPOSER_PADDING_PX

/** The box the draft needs: never less than one line, never more than six. */
export function composerHeightPx(contentPx: number): number {
  return Math.min(Math.max(contentPx, COMPOSER_EMPTY_PX), COMPOSER_MAX_PX)
}

/**
 * Size the field to its draft.
 *
 * `scrollHeight` is the height of the scrolling area, so it can only be trusted
 * for the layout that is currently applied: the box is released to its content
 * first, and because a re-wrap changes the content without changing the draft,
 * the measure runs again when the field's width changes.
 */
export function useComposerGrow(ref: RefObject<HTMLTextAreaElement | null>, draft: string): void {
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${composerHeightPx(el.scrollHeight)}px`
  }, [draft, ref])

  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver !== 'function') return
    let width = el.getBoundingClientRect().width
    const ro = new ResizeObserver(() => {
      const next = el.getBoundingClientRect().width
      if (next === width) return
      width = next
      el.style.height = 'auto'
      el.style.height = `${composerHeightPx(el.scrollHeight)}px`
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
}
