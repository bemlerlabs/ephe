'use client'

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, X } from 'lucide-react'
import { PANEL_MENU_KEYS, TAB_KEYS, Tab, TabState, relTime } from './primitives'
import { TabIcon } from './tabIcon'

/** The whole page inventory of the pane, split into two groups: the four main
 *  entries (PANEL_MENU_KEYS — their menu key is a pinned contract, P6 B1/B5) and
 *  the REMAINING pages (tasks/files/audit/trajectory/subagents/memory), which
 *  stood in no menu at all until now — evidence was reachable only through the
 *  tool row (P4 finding 1). Two separate testid prefixes, so the contract of the
 *  four keys stays measurable and the extra pages carry their own rows. */
const MAIN_KEYS = PANEL_MENU_KEYS
const EXTRA_TABS: Tab[] = TAB_KEYS.filter((tab) => !PANEL_MENU_KEYS.some((m) => m.tab === tab))

const ROW_CLASS =
  'flex items-center gap-2 px-2 py-1.5 rounded-lg text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface transition-colors text-left'
const SECTION_CLASS = 'px-2 pt-1.5 text-ui-xs uppercase tracking-wide text-ink-faint'

/** The trigger lives in panelTabBar (data-testid) — Escape returns focus to it,
 *  otherwise the user lands in no-man's-land of focus. */
function refocusAddTrigger() {
  const trigger = document.querySelector<HTMLElement>('[data-testid="panel-add-tab"]')
  trigger?.focus()
}

/**
 * The + menu: search, "open tabs" (switch/close), "recently closed"
 * (restore) and ALL pane pages on offer.
 *
 * P4 (keyboard round): the menu is now a real menu —
 *  · the trigger carries aria-haspopup/aria-expanded/aria-controls (panelTabBar),
 *  · its own focus when opening (the search field) and roving focus across every
 *    menuitem row (ArrowUp/ArrowDown/Home/End),
 *  · Tab stays closed inside the menu, Escape closes ONLY the menu and hands the
 *    focus back to the trigger (before: no menu focus, ArrowDown moved the toolbar
 *    pill, and Escape threw the whole pane shut),
 *  · rows are role="menuitem" with tabIndex -1 (only the active one is focused),
 *    sections are role="group" with a real name,
 *  · the close button is no longer an interactive island inside a menuitem button
 *    (role="button" inside role="menuitem" is invalid).
 */
export function PanelAddMenu({
  tabs,
  active,
  recent,
  labels,
  query,
  onQuery,
  onPickTab,
  onCloseTab,
  onOpenTab,
  onDismiss,
}: {
  tabs: Tab[]
  active: Tab | null
  recent: TabState['recent']
  labels: Record<Tab, string>
  query: string
  onQuery: (next: string) => void
  onPickTab: (key: Tab) => void
  onCloseTab: (key: Tab) => void
  onOpenTab: (key: Tab) => void
  onDismiss: () => void
}) {
  const { t } = useTranslation()
  const menuRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const q = query.trim().toLowerCase()
  // Search hits the label, the menu key AND the tab key — "Wiss" finds the German
  // knowledge label, "audit" finds the proof, "git" finds the changes.
  const matches = (needle: { label: string; keys: string[] }) =>
    q === '' ||
    needle.label.toLowerCase().includes(q) ||
    needle.keys.some((k) => k.toLowerCase().includes(q))
  const offered = MAIN_KEYS.filter(({ menuKey, tab }) =>
    matches({ label: labels[tab], keys: [menuKey, tab] }),
  )
  const extras = EXTRA_TABS.filter((tab) => matches({ label: labels[tab], keys: [tab] }))
  const anyOffer = offered.length + extras.length > 0

  /** Menu items in DOM order — the roving axis. */
  const itemNodes = () =>
    Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])

  // P4: focus of its own inside the menu, otherwise it stays on the trigger and
  // the arrow keys move the toolbar behind it.
  useEffect(() => {
    searchRef.current?.focus()
  }, [])

  const focusAt = (el: HTMLElement | undefined) => {
    if (el) el.focus()
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const nodes = itemNodes()
    const current = nodes.indexOf(document.activeElement as HTMLElement)
    const ring: (HTMLElement | undefined)[] = [searchRef.current ?? undefined, ...nodes]
    const ringIdx = ring.findIndex((el) => el === document.activeElement)
    switch (e.key) {
      case 'ArrowDown':
      case 'ArrowUp': {
        e.preventDefault()
        e.stopPropagation()
        if (nodes.length === 0) return
        const dir = e.key === 'ArrowDown' ? 1 : -1
        // Straight from the search field into the list (its end on ArrowUp).
        if (current < 0) {
          focusAt(e.key === 'ArrowDown' ? nodes[0] : nodes[nodes.length - 1])
          return
        }
        focusAt(nodes[(current + dir + nodes.length) % nodes.length])
        return
      }
      case 'Home':
        e.preventDefault()
        e.stopPropagation()
        focusAt(nodes[0])
        return
      case 'End':
        e.preventDefault()
        e.stopPropagation()
        focusAt(nodes[nodes.length - 1])
        return
      case 'Enter':
        // Enter in the search field puts focus on the first matching result;
        // Enter ON a row activates that row itself (a native button).
        if (current < 0 && nodes.length > 0) {
          e.preventDefault()
          e.stopPropagation()
          focusAt(nodes[0])
        }
        return
      case 'Tab': {
        // The Tab cycle inside the menu is closed — before this focus wandered
        // through the chat chrome behind the menu.
        e.preventDefault()
        e.stopPropagation()
        const dir = e.shiftKey ? -1 : 1
        const next = ringIdx < 0 ? 0 : (ringIdx + dir + ring.length) % ring.length
        focusAt(ring[next])
        return
      }
      case 'Escape':
        e.preventDefault()
        e.stopPropagation()
        onDismiss()
        refocusAddTrigger()
        return
    }
  }

  const sectionId = (name: string) => `panel-add-menu-${name}`

  return (
    <>
      <div className="fixed inset-0 z-overlay" aria-hidden="true" onClick={onDismiss} />
      <div
        ref={menuRef}
        id="panel-add-menu"
        role="menu"
        aria-label={t('agentPanel.addTab')}
        onKeyDown={onKeyDown}
        data-testid="panel-add-menu"
        className="absolute top-11 left-2 right-2 z-modal float-surface p-2 flex flex-col gap-1 max-h-96 overflow-y-auto"
      >
        <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-surface border border-hairline">
          <Search className="h-3.5 w-3.5 text-ink-faint shrink-0" aria-hidden="true" />
          <input
            ref={searchRef}
            data-testid="panel-tab-search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder={t('agentPanel.searchTabs')}
            aria-label={t('agentPanel.searchTabs')}
            className="flex-1 min-w-0 bg-transparent text-ui-xs text-foreground placeholder:text-ink-faint outline-none"
          />
        </div>
        {tabs.length > 0 && (
          <div role="group" aria-labelledby={sectionId('open')}>
            <p id={sectionId('open')} className={SECTION_CLASS}>
              {t('agentPanel.openTabsSection')}
            </p>
            {tabs.map((key) => (
              <div key={key} role="none" className="flex items-center gap-1">
                <button
                  type="button"
                  role="menuitem"
                  tabIndex={-1}
                  data-testid={`panel-open-tab-row-${key}`}
                  onClick={() => onPickTab(key)}
                  aria-label={`${labels[key]}${active === key ? ` — ${t('agentPanel.now')}` : ''}`}
                  className={`flex-1 min-w-0 flex items-center gap-2 px-2 py-1.5 rounded-lg text-ui-xs text-left transition-colors ${active === key ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground hover:bg-surface'}`}
                >
                  <TabIcon tab={key} />
                  <span className="truncate flex-1">{labels[key]}</span>
                  {active === key && (
                    <span className="text-ui-xs text-ink-faint shrink-0">
                      {t('agentPanel.now')}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  tabIndex={-1}
                  data-testid={`panel-open-tab-close-${key}`}
                  aria-label={`${t('agentPanel.closeTab')}: ${labels[key]}`}
                  title={t('agentPanel.closeTab')}
                  onClick={() => onCloseTab(key)}
                  className="grid place-items-center h-7 w-7 shrink-0 rounded-md text-ink-faint hover:text-foreground hover:bg-surface focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        {query === '' && recent.length > 0 && (
          <div role="group" aria-labelledby={sectionId('recent')}>
            <p id={sectionId('recent')} className={SECTION_CLASS}>
              {t('agentPanel.closedTabsSection')}
            </p>
            {recent.map((r) => (
              <button
                key={r.tab}
                type="button"
                role="menuitem"
                tabIndex={-1}
                data-testid={`panel-recent-${r.tab}`}
                onClick={() => onOpenTab(r.tab)}
                className={ROW_CLASS}
              >
                <TabIcon tab={r.tab} />
                <span className="truncate flex-1">{labels[r.tab]}</span>
                <span className="text-ui-xs text-ink-faint shrink-0">{relTime(r.closedAt)}</span>
              </button>
            ))}
          </div>
        )}
        {!anyOffer ? (
          <p className="px-2 py-3 text-ui-xs text-ink-faint text-center">
            {t('agentPanel.noTabMatches')}
          </p>
        ) : (
          <div role="group" aria-labelledby={sectionId('available')}>
            <p id={sectionId('available')} className={SECTION_CLASS}>
              {t('agentPanel.availableTabsSection')}
            </p>
            {offered.map(({ menuKey, tab }) => (
              <button
                key={menuKey}
                type="button"
                role="menuitem"
                tabIndex={-1}
                data-testid={`panel-new-tab-item-${menuKey}`}
                onClick={() => onOpenTab(tab)}
                className={ROW_CLASS}
              >
                <TabIcon tab={tab} />
                <span className="truncate">{labels[tab]}</span>
              </button>
            ))}
            {/* P4 finding 1: the remaining pages of the pane — before this they had
                no menu entry at all (evidence/replay/knowledge/helpers/
                tasks/files were reachable only through the tool row, the palette
                or a click on a helper). */}
            {extras.map((tab) => (
              <button
                key={tab}
                type="button"
                role="menuitem"
                tabIndex={-1}
                data-testid={`panel-page-item-${tab}`}
                onClick={() => onOpenTab(tab)}
                className={ROW_CLASS}
              >
                <TabIcon tab={tab} />
                <span className="truncate">{labels[tab]}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
