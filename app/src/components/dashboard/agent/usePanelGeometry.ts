'use client'

import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

export type Dock = 'left' | 'right'

const WIDTH_STEPS = [420, 560, 720]
const FIT_WIDTH = 420
const MIN_WIDTH = 360
const MAX_WIDTH_RATIO = 0.6

/**
 * Dock side, width and drag-resize of the agent pane — all of it persisted
 * (ephe.panel.dock / ephe.panel.width), AI-client parity.
 */
export function usePanelGeometry(open: boolean) {
  const [dock, setDock] = useState<Dock>(
    () => (localStorage.getItem('ephe.panel.dock') as Dock) || 'right',
  )
  const [width, setWidth] = useState<number>(
    () => Number(localStorage.getItem('ephe.panel.width')) || FIT_WIDTH,
  )
  const [leftOffset, setLeftOffset] = useState(0)

  // Round 9 hotfix: the left dock must NOT cover the sidebar (release bar: no
  // overlaps). Measure the sidebar width live and set it as the left offset —
  // ResizeObserver keeps it in sync (collapse/expand, resize).
  useEffect(() => {
    if (dock !== 'left' || !open) {
      setLeftOffset(0)
      return
    }
    const measure = () => {
      const sb = document.querySelector('[data-testid="chat-sidebar"]')
      setLeftOffset(sb ? sb.getBoundingClientRect().width : 0)
    }
    measure()
    const ro = new ResizeObserver(measure)
    const sb = document.querySelector('[data-testid="chat-sidebar"]')
    if (sb) ro.observe(sb)
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [dock, open])

  const toggleDock = () => {
    const next = dock === 'right' ? 'left' : 'right'
    setDock(next)
    localStorage.setItem('ephe.panel.dock', next)
  }

  const cycleWidth = () => {
    const next = WIDTH_STEPS[(WIDTH_STEPS.indexOf(width) + 1) % WIDTH_STEPS.length] ?? 560
    setWidth(next)
    localStorage.setItem('ephe.panel.width', String(next))
  }

  const fitWidth = () => {
    setWidth(FIT_WIDTH)
    localStorage.setItem('ephe.panel.width', String(FIT_WIDTH))
  }

  // Round 12: drag-resize on the panel's inner edge (360px … 60vw), persisted.
  const widthRef = useRef(width)
  widthRef.current = width

  const onResizeHandleDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = widthRef.current
    const onMove = (ev: PointerEvent) => {
      // Right dock: inner edge = the left border (drag left = wider);
      // left dock: inner edge = the right border (drag right = wider).
      const delta = dock === 'right' ? startX - ev.clientX : ev.clientX - startX
      const maxW = Math.round(window.innerWidth * MAX_WIDTH_RATIO)
      setWidth(Math.min(Math.max(startWidth + delta, MIN_WIDTH), maxW))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      localStorage.setItem('ephe.panel.width', String(widthRef.current))
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  // Round 12: the command-palette action "switch panel side" (AI-client parity).
  // Deliberately WITHOUT a deps list: the listener must re-register on EVERY
  // render, so toggleDock never sets a frozen dock side.
  useEffect(() => {
    const onToggleDock = () => toggleDock()
    window.addEventListener('ephe:panel-dock-toggle', onToggleDock)
    return () => window.removeEventListener('ephe:panel-dock-toggle', onToggleDock)
  })

  return { dock, width, leftOffset, toggleDock, cycleWidth, fitWidth, onResizeHandleDown }
}
