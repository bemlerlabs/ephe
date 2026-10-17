'use client'

import { useEffect, useRef, useState } from 'react'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { normalizeBrowserUrl } from './previewUrl'
import { Tab, TabState } from './primitives'

type Host = {
  open: boolean
  setOpen: (next: boolean) => void
  tabState: TabState
  openTab: (key: Tab) => void
}

/**
 * The ONE url pane: address value, draft, reload counter and the tab's browser
 * history (back/forward like the reference pattern).
 * P6 B5 (ref-22/24): 'browser' is now only an alias for the preview tab; external
 * http(s) and internal /api/ paths run identically.
 *
 * The panelRef belongs here because the listener's focus guard needs it; the
 * shell hangs it on the <aside>.
 */
export function usePreviewNav(host: Host) {
  const [url, setUrl] = useState('')
  const [draft, setDraft] = useState('')
  const [nonce, setNonce] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  // M1 (reference parity): the sequence lives in a ref, re-render via a version counter.
  const histRef = useRef<string[]>([])
  const histIdxRef = useRef(-1)
  const [, bumpHist] = useState(0)

  // Round 9 hotfix: the PREVIEW_OPEN_EVENT listener hangs on [] (registers once) —
  // state inside it would be STALE. Refs mirror the current state so the toggle
  // works reliably.
  const openRef = useRef(host.open)
  openRef.current = host.open
  const tabStateRef = useRef(host.tabState)
  tabStateRef.current = host.tabState
  const openTabRef = useRef(host.openTab)
  openTabRef.current = host.openTab
  const setOpenRef = useRef(host.setOpen)
  // Focus moves are deferred by 40–60 ms so the panel can mount first; the ids are
  // kept because a timer that outlives the component fires into a torn-down document.
  // CI's vitest saw exactly that: `ReferenceError: document is not defined`, thrown
  // from this file's Timeout after the test environment was already gone.
  const timersRef = useRef<number[]>([])
  const later = (fn: () => void, ms: number) => {
    const id = window.setTimeout(() => {
      timersRef.current = timersRef.current.filter((t) => t !== id)
      fn()
    }, ms)
    timersRef.current.push(id)
  }
  setOpenRef.current = host.setOpen

  const pushHist = (u: string) => {
    const trimmed = u.trim()
    if (!trimmed) return
    histRef.current = [...histRef.current.slice(0, histIdxRef.current + 1), trimmed]
    histIdxRef.current = histRef.current.length - 1
    bumpHist((v) => v + 1)
  }

  const gotoHist = (nextIdx: number) => {
    const u = histRef.current[nextIdx]
    if (u === undefined) return
    histIdxRef.current = nextIdx
    setUrl(u)
    try {
      setDraft(decodeURIComponent(u))
    } catch {
      setDraft(u)
    }
    bumpHist((v) => v + 1)
    later(() => inputRef.current?.focus(), 40)
  }

  useEffect(() => {
    const onOpen = (e: Event) => {
      const detail = (e as CustomEvent<{ url?: string; tab?: Tab; toggle?: boolean }>).detail
      // Round G: the header toggle collapses/expands — the tab inventory stays intact.
      if (
        detail?.toggle &&
        openRef.current &&
        !detail.url &&
        (!detail.tab || detail.tab === tabStateRef.current.active)
      ) {
        setOpenRef.current(false)
        return
      }
      if (detail?.url !== undefined) {
        // P6 B5: every URL into the ONE url pane (ref-22/24) — external http(s)
        // URLs (source chips, palette) and internal /api/ paths behave identically
        // (address bar, history, reload).
        setUrl(detail.url)
        // Show a decoded path in the URL bar (%2F… is unreadable); safe fallback
        try {
          setDraft(decodeURIComponent(detail.url))
        } catch {
          setDraft(detail.url)
        }
        pushHist(detail.url)
        openTabRef.current(detail.tab === 'browser' ? 'preview' : (detail.tab ?? 'preview'))
      } else if (detail?.tab) openTabRef.current(detail.tab)
      setOpenRef.current(true)
      // The follow-through into the address bar only applies while the user is
      // still outside the panel (source chip, palette, chat). If the keyboard
      // already stands inside the panel — say in an open overflow menu — this
      // focus after 60 ms would be a theft.
      if (detail?.url !== undefined) {
        later(() => {
          const active = document.activeElement
          if (panelRef.current && active && panelRef.current.contains(active)) return
          inputRef.current?.focus()
        }, 60)
      }
    }
    window.addEventListener(PREVIEW_OPEN_EVENT, onOpen)
    return () => {
      window.removeEventListener(PREVIEW_OPEN_EVENT, onOpen)
      // Unmount cancels every pending focus: the DOM it was aiming at is gone.
      timersRef.current.forEach((id) => window.clearTimeout(id))
      timersRef.current = []
    }
  }, [])

  const load = () => {
    // P6 B5: scheme-less inputs get their protocol (example.com → https://,
    // localhost → http://) — one pane, both URL worlds.
    const next = normalizeBrowserUrl(draft)
    setUrl(next)
    pushHist(next)
  }

  const reload = () => setNonce((n) => n + 1)

  return {
    panelRef,
    url,
    setUrl,
    draft,
    setDraft,
    nonce,
    inputRef,
    load,
    reload,
    recent: [...histRef.current].reverse().slice(0, 8),
    pickRecent: (i: number) => gotoHist(histRef.current.length - 1 - i),
    back: () => gotoHist(histIdxRef.current - 1),
    forward: () => gotoHist(histIdxRef.current + 1),
    canBack: histIdxRef.current > 0,
    canForward: histIdxRef.current >= 0 && histIdxRef.current < histRef.current.length - 1,
  }
}
