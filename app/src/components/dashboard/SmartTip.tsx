// H round H1 (2026-09-07): reference-B-style hover popups — a small, delayed
// explanation box (title + line) for everything the UI does not explain itself:
// tool cards (what does this tool do?), review status chips (what means M/?/D?),
// panel tab pills, header toggles. Keyboard focus shows it without delay
// (a11y); on touch devices (no hover) it stays hidden.
// The popup renders as a PORTAL on document.body with real fixed positioning:
// ancestor overflow clipping (header, scroll and card containers) plus
// transform/backdrop stacking contexts would otherwise make it invisible —
// exactly the error class the judge gate exposed in the G round.
import { useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export interface SmartTipContent {
  title: string
  body?: string
}

type Side = 'top' | 'bottom'

const HOVER_DELAY_MS = 350
const POPUP_WIDTH = 240 // px, set by hand instead of w-60 because of the fixed style

export default function SmartTip({
  tip,
  side = 'top',
  children,
  testId,
  block = false,
}: {
  tip: SmartTipContent
  side?: Side
  children: ReactNode
  testId?: string
  /** Block elements (e.g. tool cards) wrap instead of using inline-flex. */
  block?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number } | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapRef = useRef<HTMLSpanElement>(null)

  const measure = () => {
    const el = wrapRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const left = Math.min(
      Math.max(8, r.left + r.width / 2 - POPUP_WIDTH / 2),
      window.innerWidth - POPUP_WIDTH - 8,
    )
    setPos(
      side === 'bottom'
        ? { left, top: r.bottom + 8 }
        : { left, bottom: window.innerHeight - r.top + 8 },
    )
  }
  const scheduleOpen = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      measure()
      setOpen(true)
    }, HOVER_DELAY_MS)
  }
  const openNow = () => {
    measure()
    setOpen(true)
  }
  const close = () => {
    if (timer.current) clearTimeout(timer.current)
    setOpen(false)
  }

  return (
    <span
      ref={wrapRef}
      className={block ? 'relative block' : 'relative inline-flex'}
      data-testid={testId}
      onMouseEnter={scheduleOpen}
      onMouseLeave={close}
      onFocus={openNow}
      onBlur={close}
    >
      {children}
      {open &&
        pos &&
        createPortal(
          <span
            role="tooltip"
            data-testid="smart-tip-popup"
            style={{
              position: 'fixed',
              left: pos.left,
              top: pos.top,
              bottom: pos.bottom,
              width: POPUP_WIDTH,
            }}
            className="z-modal hidden lg:block float-surface px-3 py-2 pointer-events-none"
          >
            <span className="block text-ui-sm font-semibold text-foreground/90 leading-snug">
              {tip.title}
            </span>
            {tip.body && (
              <span className="block text-ui-sm text-ink-soft leading-snug mt-0.5">{tip.body}</span>
            )}
          </span>,
          document.body,
        )}
    </span>
  )
}
