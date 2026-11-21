/**
 * The pet moves where the user puts it.
 *
 * The offset is a `translate` on the figure's own box, so the layout it was
 * placed in keeps its anchor: the pet leaves the corner without dragging the
 * copilot chip or the popover out of their own coordinates. The offset is kept
 * as a fraction of the viewport and clamped on every resize, so a pet parked
 * near an edge of a wide window stays visible in a narrow one.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'ephe.companion.offset.v1'
const DRAG_THRESHOLD = 4
const EDGE_MARGIN = 8

export interface Offset {
  x: number
  y: number
}

interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

interface Box {
  left: number
  top: number
  width: number
  height: number
}

/** The nearest ancestor that clips its children, or the viewport. The chat
 *  pane clips, so a pet parked past its edge would be gone, not just far. */
function clipBox(el: HTMLElement): Box {
  let node = el.parentElement
  while (node && node !== document.body) {
    const style = window.getComputedStyle(node)
    if (style.overflowX !== 'visible' || style.overflowY !== 'visible') {
      const rect = node.getBoundingClientRect()
      return { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
    }
    node = node.parentElement
  }
  return { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }
}

/** The offsets that keep the box inside `container` when its home corner is at
 *  `home`. */
export function offsetBounds(home: Box, container: Box): Bounds {
  const left = home.left - container.left
  const top = home.top - container.top
  return {
    minX: EDGE_MARGIN - left,
    maxX: container.width - EDGE_MARGIN - home.width - left,
    minY: EDGE_MARGIN - top,
    maxY: container.height - EDGE_MARGIN - home.height - top,
  }
}

export function clampOffset(offset: Offset, bounds: Bounds): Offset {
  return {
    x: Math.min(bounds.maxX, Math.max(bounds.minX, offset.x)),
    y: Math.min(bounds.maxY, Math.max(bounds.minY, offset.y)),
  }
}

function readStored(): Offset | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<Offset>
    if (typeof parsed.x !== 'number' || typeof parsed.y !== 'number') return null
    if (!Number.isFinite(parsed.x) || !Number.isFinite(parsed.y)) return null
    return { x: parsed.x * window.innerWidth, y: parsed.y * window.innerHeight }
  } catch {
    return null
  }
}

function writeStored(offset: Offset): void {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ x: offset.x / window.innerWidth, y: offset.y / window.innerHeight }),
    )
  } catch {
    /* a private window without storage keeps the pet where the hand left it */
  }
}

export interface CompanionDrag {
  /** Inline style for the movable box. */
  style: { translate: string } | undefined
  dragging: boolean
  handlers: {
    onPointerDown: (event: React.PointerEvent<HTMLElement>) => void
    onPointerMove: (event: React.PointerEvent<HTMLElement>) => void
    onPointerUp: (event: React.PointerEvent<HTMLElement>) => void
    onPointerCancel: (event: React.PointerEvent<HTMLElement>) => void
    onClickCapture: (event: React.MouseEvent<HTMLElement>) => void
    onDoubleClick: (event: React.MouseEvent<HTMLElement>) => void
  }
}

export function useCompanionDrag(
  ref: React.RefObject<HTMLElement | null>,
  /** True while the drag may start from `event.target`. */
  canStart: (target: EventTarget | null) => boolean,
): CompanionDrag {
  const [offset, setOffset] = useState<Offset | null>(null)
  /** The same offset for the handlers: a pointermove and the pointerup that
   *  follows it land before the next render. */
  const offsetRef = useRef<Offset | null>(null)
  const [dragging, setDragging] = useState(false)
  const start = useRef<{
    pointer: number
    x: number
    y: number
    offset: Offset
    bounds: Bounds
    moved: boolean
  } | null>(null)
  const suppressClick = useRef(false)

  const boundsNow = useCallback((): Bounds | null => {
    const el = ref.current
    if (!el) return null
    const rect = el.getBoundingClientRect()
    const applied = offsetRef.current ?? { x: 0, y: 0 }
    const home = {
      left: rect.left - applied.x,
      top: rect.top - applied.y,
      width: rect.width,
      height: rect.height,
    }
    return offsetBounds(home, clipBox(el))
  }, [ref])

  const place = useCallback((next: Offset | null) => {
    offsetRef.current = next
    setOffset(next)
  }, [])

  useEffect(() => {
    const stored = readStored()
    if (!stored) return
    // The saved offset was measured in another window; clamp it to this one
    // once the box has a layout, or a pet parked at a wide edge is offscreen.
    const frame = requestAnimationFrame(() => {
      // No layout, nothing to clamp against: the box is not on screen yet.
      if (!ref.current?.getClientRects().length) {
        place(stored)
        return
      }
      const bounds = boundsNow()
      place(bounds ? clampOffset(stored, bounds) : stored)
    })
    return () => cancelAnimationFrame(frame)
  }, [boundsNow, place, ref])

  const viewport = useRef({ width: window.innerWidth, height: window.innerHeight })

  useEffect(() => {
    const onResize = () => {
      if (
        window.innerWidth === viewport.current.width &&
        window.innerHeight === viewport.current.height
      ) {
        return
      }
      viewport.current = { width: window.innerWidth, height: window.innerHeight }
      const bounds = boundsNow()
      const el = ref.current
      if (!bounds || !el) return
      const current = offsetRef.current
      if (!current) return
      const next = clampOffset(current, bounds)
      if (next.x === current.x && next.y === current.y) return
      place(next)
      writeStored(next)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [boundsNow, place, ref])

  const onPointerDown = (event: React.PointerEvent<HTMLElement>) => {
    if (event.button !== 0 || !canStart(event.target)) return
    const bounds = boundsNow()
    const el = ref.current
    if (!bounds || !el) return
    start.current = {
      pointer: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      offset: offsetRef.current ?? { x: 0, y: 0 },
      bounds,
      moved: false,
    }
    el.setPointerCapture?.(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    const active = start.current
    if (!active || active.pointer !== event.pointerId) return
    const dx = event.clientX - active.x
    const dy = event.clientY - active.y
    if (!active.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    active.moved = true
    setDragging(true)
    place(clampOffset({ x: active.offset.x + dx, y: active.offset.y + dy }, active.bounds))
  }

  const finish = (event: React.PointerEvent<HTMLElement>) => {
    const active = start.current
    if (!active || active.pointer !== event.pointerId) return
    start.current = null
    setDragging(false)
    ref.current?.releasePointerCapture?.(event.pointerId)
    if (!active.moved) return
    // The click that follows a drag belongs to the drag: it must not open the
    // panel the user was only trying to move out of the way.
    suppressClick.current = true
    const current = offsetRef.current
    if (current) writeStored(current)
  }

  const onClickCapture = (event: React.MouseEvent<HTMLElement>) => {
    if (suppressClick.current) {
      suppressClick.current = false
      event.stopPropagation()
      event.preventDefault()
      return
    }
    // A double click is the reset gesture; its first click must not toggle.
    if (event.detail > 1) {
      event.stopPropagation()
      event.preventDefault()
    }
  }

  const onDoubleClick = (event: React.MouseEvent<HTMLElement>) => {
    if (!canStart(event.target) || dragging) return
    place(null)
    try {
      window.localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* nothing stored, nothing to remove */
    }
  }

  return {
    style: offset ? { translate: `${offset.x.toFixed(1)}px ${offset.y.toFixed(1)}px` } : undefined,
    dragging,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: finish,
      onPointerCancel: finish,
      onClickCapture,
      onDoubleClick,
    },
  }
}
