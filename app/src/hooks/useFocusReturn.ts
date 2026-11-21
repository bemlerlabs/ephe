/**
 * Ephe — the focus contract of an ephemeral surface (Wave 10, persona 06).
 *
 * Measured by `app/e2e/walkthrough/persona-06-tastatur.spec.ts`: the command
 * palette and the artifact rail both declare `role="dialog" aria-modal="true"`
 * and neither honoured it — Tab walked out of the palette after 5 stops and out
 * of the rail after 10, nothing behind them went inert, and closing a surface
 * opened from another one (settings opened from the palette) dropped focus onto
 * `<body>`. The settings overlay (`components/dashboard/settings/index.tsx`)
 * already did all of it correctly; this hook is that pattern, extracted, so the
 * next surface inherits it instead of growing a second, divergent variant.
 *
 * The contract, in the order it runs:
 *   (a) opening a modal surface moves focus into it (first Tab stop, else the
 *       container itself — give the container `tabIndex={-1}`),
 *   (b) Tab / Shift+Tab stay inside while it is modal,
 *   (c) everything outside gets `inert` (plus `aria-hidden` as the fallback for
 *       engines without inert support),
 *   (d) closing hands focus back to the invoker — and when the invoker is gone
 *       by then (the palette unmounts while the settings overlay it opened is
 *       still standing) to a stable target, never to `<body>`.
 *
 * Usage:
 *
 *   const containerRef = useRef<HTMLDivElement>(null)
 *   const { onKeyDown, releaseFocus } = useFocusReturn({ active: open, containerRef })
 *   ...
 *   <div ref={containerRef} tabIndex={-1} role="dialog" aria-modal="true" onKeyDown={onKeyDown}>
 *
 * `releaseFocus()` must be called in the same task that closes the surface (the
 * Escape/commit/close handler) — the handback then happens while the invoker still
 * exists, which is what keeps focus off `<body>` when the next modal is already
 * on its way in. The effect cleanup calls it again for closes that come from the
 * parent; both are idempotent.
 */
import { useCallback, useEffect, useRef } from 'react'

/** Every Tab stop, exactly the set the walkthrough spec counts (`tabIndex >= 0`). */
export const FOCUSABLE_SELECTOR = 'a[href],button,input,select,textarea,[tabindex]'

/**
 * Stable handback targets, best first. `#ephe-chat-input` is the app's primary
 * action (the skip link in `App.tsx` targets it), `#main-content` the chat
 * landmark — both live in the shell, so they survive a surface unmounting under
 * them. A surface that knows a better anchor of its own marks it with
 * `[data-focus-return-target]` and wins.
 */
export const STABLE_FOCUS_TARGETS = [
  '[data-focus-return-target]',
  '#ephe-chat-input',
  '#main-content',
  '[role="main"]',
]

/** Is the element a programmatic Tab stop? No geometry: jsdom has no layout and
 *  a `offsetParent`/visibility test would empty the list there (and in tests). */
export function isTabStop(el: HTMLElement): boolean {
  if (el.hasAttribute('disabled') || el.hasAttribute('hidden')) return false
  return el.tabIndex >= 0
}

/** The Tab stops inside `container`, in DOM order. */
export function tabStops(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(isTabStop)
}

/**
 * Where focus goes when the invoker is unusable — unmounted, `<body>`, or inside
 * a subtree another modal made inert. Never returns `<body>`: a fallback that
 * resolves to the body is exactly the defect this hook exists to remove, so no
 * target at all is the honest answer (focus then simply stays where it is).
 */
export function stableFocusTarget(doc: Document = document): HTMLElement | null {
  for (const selector of STABLE_FOCUS_TARGETS) {
    const el = doc.querySelector<HTMLElement>(selector)
    if (!el || !el.isConnected || el === doc.body) continue
    if (el.closest('[inert]')) continue
    return el
  }
  return null
}

/**
 * Makes everything outside `node` unreachable (keyboard, pointer, AT): the
 * siblings along the ancestor chain get `inert` and `aria-hidden`, everything
 * else is left alone. Same walk as the settings overlay's (one behaviour, not
 * two), so a later settings refactor can import this one. Returns the release.
 */
export function makeBackgroundInert(
  node: HTMLElement,
  doc: Document = node.ownerDocument,
): () => void {
  const touched: HTMLElement[] = []
  let node2: HTMLElement | null = node
  while (node2 && node2 !== doc.body) {
    const parent: HTMLElement | null = node2.parentElement
    if (!parent) break
    for (const sibling of Array.from(parent.children)) {
      const el = sibling as HTMLElement
      if (el === node2 || el.contains(node)) continue
      // Already marked: it belongs to another surface's inert set.
      if (el.hasAttribute('inert') || el.getAttribute('aria-hidden') === 'true') continue
      el.setAttribute('inert', '')
      el.setAttribute('aria-hidden', 'true')
      touched.push(el)
    }
    node2 = parent
  }
  return () => {
    for (const el of touched) {
      el.removeAttribute('inert')
      el.removeAttribute('aria-hidden')
    }
    touched.length = 0
  }
}

export interface FocusReturnOptions {
  /** The surface is open right now. */
  active: boolean
  /** The element that holds the surface's focusables (the aria-modal dialog). */
  containerRef: React.RefObject<HTMLElement | null>
  /** The surface claims `aria-modal`: trap Tab, inert the background (default true). */
  modal?: boolean
  /** Move focus into the surface when it opens (default true). */
  autoFocus?: boolean
}

export interface FocusReturnApi {
  /** Put this on the surface root: it is the Tab/Shift+Tab trap while modal. */
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void
  /** End the modal state in this task: lift the background inert and hand focus
   *  back to the invoker (or the stable target). Idempotent. */
  releaseFocus: () => void
  /** The element focus would be handed back to right now (introspection seam). */
  restoreTarget: () => HTMLElement | null
}

export function useFocusReturn({
  active,
  containerRef,
  modal = true,
  autoFocus = true,
}: FocusReturnOptions): FocusReturnApi {
  const invokerRef = useRef<HTMLElement | null>(null)
  // Refs, not dependencies: the recorder must read the CURRENT state without the
  // listener being torn down and rebuilt on every open/close.
  const activeRef = useRef(active)
  activeRef.current = active
  const releaseRef = useRef<() => void>(() => {})

  // (d) The invoker: the last element that held focus while this surface was
  // closed. A recorder rather than one read at open time, because the surface
  // can itself be opened from inside another modal — the palette's combobox is
  // the settings overlay's invoker, and it is gone by the time settings closes.
  useEffect(() => {
    const onFocusIn = (event: FocusEvent) => {
      if (activeRef.current) return
      const el = event.target as HTMLElement | null
      if (!el || el === document.body) return
      if (containerRef.current?.contains(el)) return
      invokerRef.current = el
    }
    window.addEventListener('focusin', onFocusIn, true)
    return () => window.removeEventListener('focusin', onFocusIn, true)
  }, [containerRef])

  const restoreTarget = useCallback((): HTMLElement | null => {
    const invoker = invokerRef.current
    const usable =
      invoker && invoker.isConnected && invoker !== document.body && !invoker.closest('[inert]')
    return usable ? invoker : stableFocusTarget()
  }, [])

  const handBack = useCallback(() => {
    restoreTarget()?.focus()
  }, [restoreTarget])

  const releaseFocus = useCallback(() => {
    releaseRef.current()
    handBack()
  }, [handBack])

  // (b) Tab stays inside. The trap only reacts when focus would leave through an
  // edge; everything in between is the browser's own (correct) order.
  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLElement>) => {
      if (!modal || event.key !== 'Tab') return
      const container = containerRef.current
      if (!container) return
      const stops = tabStops(container)
      if (stops.length === 0) {
        // Nothing to focus inside: swallowing Tab is the honest answer, the
        // alternative is handing focus to the page behind an aria-modal surface.
        event.preventDefault()
        return
      }
      const first = stops[0]!
      const last = stops[stops.length - 1]!
      const current = document.activeElement as HTMLElement | null
      const index = current ? stops.indexOf(current) : -1
      const atEdge = event.shiftKey ? index <= 0 : index === -1 || index === stops.length - 1
      if (!atEdge) return
      event.preventDefault()
      ;(event.shiftKey ? last : first).focus()
    },
    [modal, containerRef],
  )

  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return

    // The invoker, second chance: if nothing was recorded (the app had no focus
    // at all when the surface opened — the walkthrough's palette case), take
    // whatever holds focus before this hook moves it in.
    const outside = document.activeElement as HTMLElement | null
    if (
      !invokerRef.current &&
      outside &&
      outside !== document.body &&
      !container.contains(outside)
    ) {
      invokerRef.current = outside
    }

    // (a) focus in — first Tab stop, else the container itself.
    if (autoFocus) {
      const stops = tabStops(container)
      if (stops.length) stops[0]!.focus()
      else container.focus()
    }

    // (c) background inert. Applied after (a): inerting can blur an element that
    // was focused outside, and doing it in this order means the surface never
    // stands open with focus still behind it.
    let release = () => {}
    if (modal) {
      release = makeBackgroundInert(container)
      if (!container.contains(document.activeElement)) container.focus()
    }
    releaseRef.current = release

    return () => {
      release()
      releaseRef.current = () => {}
      handBack()
    }
  }, [active, autoFocus, modal, containerRef, handBack])

  return { onKeyDown, releaseFocus, restoreTarget }
}
