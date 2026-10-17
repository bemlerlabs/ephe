'use client'

import { useEffect, useState } from 'react'

/**
 * F10 (round 14): the frost pulse only as a short attention signal after opening
 * (3 cycles of 7 s each), then quiet — never a permanent repaint on the panel.
 */
export function usePanelPulse(open: boolean) {
  const [pulse, setPulse] = useState(false)
  useEffect(() => {
    if (!open) {
      setPulse(false)
      return
    }
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return
    setPulse(true)
    const t = setTimeout(() => setPulse(false), 21_000)
    return () => clearTimeout(t)
  }, [open])
  return pulse
}
