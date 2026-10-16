'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { Tab, TAB_KEYS, TabState, readJson } from './primitives'

/**
 * Digit → page (P4 finding 3): the number means a position in the VISIBLE bar. If
 * the bar is still empty at that position, the digit opens the same page as before
 * (its index in TAB_KEYS) — it then moves to that position.
 * ⌘0 would be the tenth pill (TAB_KEYS.length), as in a browser; the inventory
 * carries nine pages since the Steps tab left, so ⌘1–⌘9 are the row.
 */
export function resolvePanelTabByDigit(open: Tab[], digit: number): Tab | null {
  if (digit < 1 || digit > TAB_KEYS.length) return null
  return open[digit - 1] ?? TAB_KEYS[digit - 1] ?? null
}

function isEditable(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || (el as HTMLElement).isContentEditable === true
}

/**
 * The active tab, stored JSON-encoded like tabs/recent. A bare string from a
 * session that predates the change is still accepted, so an upgrade keeps the
 * page it was on instead of falling back to the first.
 */
function readActiveTab(): Tab | null {
  const raw = localStorage.getItem('ephe.panel.activeTab')
  if (!raw) return null
  try {
    return JSON.parse(raw) as Tab
  } catch {
    return raw as Tab
  }
}

/**
 * The pane's tab inventory: opened pills, the active tab and the recently closed
 * ones. Persisted across the session (ephe.panel.tabs /
 * .activeTab / .recent), so a restart brings back the same pages.
 *
 * P4: this file is also the source of the ⌘1–⌘9 binding. The number can only be
 * right here, because only the registry knows the order in which the bar opened;
 * useCommandPalette (registration order) is intercepted in the capture path for
 * that reason.
 */
export function useTabRegistry() {
  const [tabState, setTabState] = useState<TabState>(() => {
    // P6 B5: persisted 'browser' tabs (before the dedup) land in the URL pane —
    // alias first, then filter against TAB_KEYS.
    const initialTabs = readJson<Tab[]>('ephe.panel.tabs', ['preview']).map((k) =>
      k === 'browser' ? 'preview' : k,
    )
    const filtered = initialTabs.filter((k) => TAB_KEYS.includes(k))
    const wanted = readActiveTab()
    const wantedNorm = wanted === 'browser' ? 'preview' : wanted
    const active = wantedNorm && filtered.includes(wantedNorm) ? wantedNorm : (filtered[0] ?? null)
    const recent = readJson<{ tab: Tab; closedAt: number }[]>('ephe.panel.recent', [])
      .filter((r) => TAB_KEYS.includes(r.tab))
      .map((r) => ({ ...r, tab: r.tab === 'browser' ? ('preview' as Tab) : r.tab }))
    return { open: filtered, active, recent }
  })
  const [menuOpen, setMenuOpen] = useState(false)
  const [tabQuery, setTabQuery] = useState('')

  // Persist the tab inventory so a restart reopens the same pages (reference parity).
  useEffect(() => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(tabState.open))
    if (tabState.active) {
      localStorage.setItem('ephe.panel.activeTab', JSON.stringify(tabState.active))
    }
    localStorage.setItem('ephe.panel.recent', JSON.stringify(tabState.recent))
  }, [tabState])

  // The listener attaches once ([]) — the state moves into a ref so the digit
  // always addresses the CURRENT bar (the usePreviewNav pattern).
  const openRef = useRef(tabState.open)
  openRef.current = tabState.open

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return
      const digit = e.key === '0' ? TAB_KEYS.length : Number(e.key)
      if (!Number.isInteger(digit) || digit < 1 || digit > TAB_KEYS.length) return
      if (isEditable(e.target as Element | null)) return
      // A modal dialog (settings) or an open menu holds the keyboard — the digit
      // belongs there, not behind the dialog.
      if (document.querySelector('[role="dialog"][aria-modal="true"], [role="menu"]')) return
      const tab = resolvePanelTabByDigit(openRef.current, digit)
      if (!tab) return
      e.preventDefault()
      // Capture + stopPropagation: the bar is the single source for the number.
      // Without this interception useCommandPalette would additionally open
      // TAB_KEYS[n-1] — exactly the confusion P4 finding 3 measured.
      e.stopPropagation()
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab, toggle: true } }))
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [])

  const openTab = useCallback((key: Tab) => {
    setTabState((prev) => ({
      open: prev.open.includes(key) ? prev.open : [...prev.open, key],
      active: key,
      recent: prev.recent.filter((r) => r.tab !== key),
    }))
    setMenuOpen(false)
  }, [])

  const closeTab = useCallback((key: Tab) => {
    setTabState((prev) => {
      const rest = prev.open.filter((k) => k !== key)
      return {
        open: rest,
        active: prev.active === key ? (rest[rest.length - 1] ?? null) : prev.active,
        recent: [
          { tab: key, closedAt: Date.now() },
          ...prev.recent.filter((r) => r.tab !== key),
        ].slice(0, 8),
      }
    })
  }, [])

  const selectTab = useCallback((key: Tab) => {
    setTabState((prev) => ({ ...prev, active: key }))
  }, [])

  return {
    tabState,
    openTab,
    closeTab,
    selectTab,
    menuOpen,
    setMenuOpen,
    tabQuery,
    setTabQuery,
  }
}
