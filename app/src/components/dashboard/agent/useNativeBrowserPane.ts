'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listenNativeBrowser,
  openNativeBrowser,
  setNativeBrowserBounds,
  setNativeBrowserVisible,
  usesNativeBrowser,
  type BrowserBounds,
} from '@/lib/nativeBrowser'

/**
 * Attach the native page to the panel's frame area (W1).
 *
 * A child WebView knows nothing of CSS: it sits rigidly in window coordinates
 * above the main WebView. So three things have to hold —
 *  1. geometry: every resize of the frame goes out as bounds,
 *  2. visibility: hidden while the frame is empty, smaller than 0, or an overlay
 *     (dialog, menu, palette) would sit on top of it — no z-index of the app can
 *     overtake a child WebView,
 *  3. honesty: the loading state comes from the real load events, not from the
 *     `onLoad` of an iframe that reports "done" for an empty box too.
 */

/** Everything that may sit on top of a child WebView in the surface. */
const OVERLAY_SELECTOR =
  '[role="dialog"],[role="alertdialog"],[role="menu"],[role="listbox"],[role="tooltip"],[data-radix-portal],[aria-modal="true"]'

const sameBounds = (a: BrowserBounds, b: BrowserBounds) =>
  Math.abs(a.x - b.x) < 0.5 &&
  Math.abs(a.y - b.y) < 0.5 &&
  Math.abs(a.width - b.width) < 0.5 &&
  Math.abs(a.height - b.height) < 0.5

export function useNativeBrowserPane(url: string, nonce: number, maxWidth?: number) {
  const regionRef = useRef<HTMLDivElement | null>(null)
  const native = usesNativeBrowser(url)
  const [loading, setLoading] = useState(false)
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const lastBounds = useRef<BrowserBounds | null>(null)
  const shownRef = useRef(false)

  const measure = useCallback((): BrowserBounds | null => {
    const el = regionRef.current
    if (!el) return null
    const r = el.getBoundingClientRect()
    if (r.width < 1 || r.height < 1) return null
    // device width applies here too: the child WebView has no CSS, so the frame's
    // width is clamped and centred.
    const width = maxWidth ? Math.min(r.width, maxWidth) : r.width
    return { x: r.x + (r.width - width) / 2, y: r.y, width, height: r.height }
  }, [maxWidth])

  // 1 + 2: geometry and visibility follow the frame along.
  useEffect(() => {
    if (!native) {
      setLoading(false)
      return
    }
    const el = regionRef.current
    let frame = 0

    const sync = () => {
      const bounds = measure()
      const visible = !!bounds && !document.querySelector(OVERLAY_SELECTOR)
      if (bounds && (!lastBounds.current || !sameBounds(lastBounds.current, bounds))) {
        lastBounds.current = bounds
        void setNativeBrowserBounds(bounds)
      }
      if (visible !== shownRef.current) {
        shownRef.current = visible
        void setNativeBrowserVisible(visible)
      }
    }

    const schedule = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(sync)
    }

    const ro = new ResizeObserver(schedule)
    if (el) ro.observe(el)
    window.addEventListener('resize', schedule)
    window.addEventListener('scroll', schedule, true)

    // Overlays (dialog, menu, palette) appear in the DOM without any change to the
    // frame's geometry — without this observer the web page would sit on top of
    // every mask.
    const mo = new MutationObserver(schedule)
    mo.observe(document.body, { childList: true, subtree: true })

    schedule()
    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      mo.disconnect()
      window.removeEventListener('resize', schedule)
      window.removeEventListener('scroll', schedule, true)
    }
  }, [native, measure])

  // address (re)loaded: bounds first, so the page never paints briefly inside
  // the old edge.
  useEffect(() => {
    if (!native) return
    const bounds = measure() ?? lastBounds.current
    if (!bounds) return
    lastBounds.current = bounds
    setLoading(true)
    setError(null)
    shownRef.current = true
    void openNativeBrowser(url, bounds).catch((e: unknown) => {
      setLoading(false)
      setError(e instanceof Error ? e.message : String(e))
    })
  }, [native, url, nonce, measure])

  // the tab leaves the view: hide it but keep the page state — coming back means
  // being at the top of google.com again, not loading it from scratch.
  useEffect(
    () => () => {
      if (shownRef.current) {
        shownRef.current = false
        void setNativeBrowserVisible(false)
      }
    },
    // nonce/url change without a demount — the cleanup only counts on leaving.
    [],
  )

  useEffect(() => {
    if (!native) return
    return listenNativeBrowser((event) => {
      if (event.kind === 'load') setLoading(event.phase === 'started')
      else if (event.kind === 'title') setTitle(event.title)
      else if (event.kind === 'navigation') setLoading(true)
      else if (event.kind === 'new-window' && event.url && lastBounds.current) {
        // target="_blank" stays inside the pane instead of opening a window
        // nobody controls — the user sees where the link leads.
        setLoading(true)
        void openNativeBrowser(event.url, lastBounds.current).catch(() => setLoading(false))
      }
    })
  }, [native])

  return { regionRef, native, loading, title, error }
}
