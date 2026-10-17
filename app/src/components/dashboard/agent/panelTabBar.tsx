'use client'

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Maximize2, PanelLeftClose, PanelRightClose, Plus, X } from 'lucide-react'
import { Tab } from './primitives'
import { agentTabDomIds, TabPill } from './tabsTabPill'
import { TabIcon } from './tabIcon'
import { useTabTips } from './tabChrome'
import type { Dock } from './usePanelGeometry'

// R2 §4.4 point 4: the buttons were p-1.5 with an h-4 icon = 28 px, with no
// focus-visible class and no touch floor, even though this file comments 44 px.
// Now min-h-7 (28 px) as a guarantee, max-lg:min-h-11 (44 px) on touch, plus the
// repo focus ring (the same pattern as agent/previewTab.tsx).
const BUTTON_CLASS =
  'inline-grid place-items-center p-1.5 min-h-7 rounded-md text-ink-soft hover:text-foreground hover:bg-surface transition-colors shrink-0 @max-[26rem]:min-h-11 @max-[26rem]:min-w-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2'

/** A shortcut's digit sits on the pill's position (P4 finding 3): ⌘1–⌘9 are
 *  the positions of the visible bar, ⌘0 the tenth pill — the same rule
 *  useTabRegistry applies when the key is pressed. */
export function pillPositionDigit(index: number, total: number): number | null {
  const pos = index + 1
  if (pos <= 9) return pos
  if (pos === 10 && total >= 10) return 0
  return null
}

/**
 * Tab bar — R20: real tab semantics (role=tablist/tab + aria-selected).
 * R2 §4.4: the role now sits on the clickable `button` itself (tabsTabPill), not
 * on a wrapping div that merely behaves like one. The active pill points at the
 * panel through aria-controls (panel.tsx, id from agentTabDomIds); only it is
 * tabbable (roving tabindex), left/right arrows move the selection.
 * P4 (keyboard round): the + button is a real menu trigger
 * (aria-haspopup/aria-expanded/aria-controls) and opens on ArrowDown.
 * DD-11: at a narrow viewport (mobile panel ~371px) the bar clipped with no way to
 * scroll — it is now horizontally scrollable (scrollbar hidden, keyboard/touch
 * kept) with undisabled targets at least 44px wide.
 * Parity harness: the tab bar sits flush at the top of the panel edge (y=0); the
 * fixed panel (top:0, height:100%) overlaps the header on the right so that no
 * gap remains between the window's top edge and the tab bar.
 */
export function PanelTabBar({
  tabs,
  active,
  labels,
  dock,
  menuOpen,
  onSelect,
  onCloseTab,
  onToggleMenu,
  onCollapse,
  onCycleWidth,
  onToggleDock,
}: {
  tabs: Tab[]
  active: Tab | null
  labels: Record<Tab, string>
  dock: Dock
  menuOpen: boolean
  onSelect: (key: Tab) => void
  onCloseTab: (key: Tab) => void
  onToggleMenu: () => void
  onCollapse: () => void
  onCycleWidth: () => void
  onToggleDock: () => void
}) {
  const { t } = useTranslation()
  const tip = useTabTips()
  const barRef = useRef<HTMLDivElement>(null)
  // Roving tabindex: with no active tab (which happens when persistence reports a
  // tab that is open but not active) the first pill stays tabbable — otherwise the
  // list can no longer be reached by keyboard.
  const tabbable = active ?? tabs[0] ?? null

  // A closed pill removes its close button — the focus holder — from the DOM, so
  // the keyboard walk would end on <body>. Focus returns to the active pill, or to
  // the first one when a background tab was closed.
  const restoreFocus = useRef(false)
  useEffect(() => {
    if (!restoreFocus.current) return
    restoreFocus.current = false
    const key = active ?? tabs[0]
    if (!key) return
    barRef.current?.querySelector<HTMLElement>(`#${agentTabDomIds.tab(key)}`)?.focus()
  }, [tabs, active])

  /**
   * R2 §4.4 point 3: left/right arrows move the selection and take the focus with
   * them. preventDefault + stopPropagation is mandatory — chat/model.ts has a
   * global arrow listener (session switching) that only pauses inside a
   * [role=tablist]. Home/End jump to the ends: with the roving tabindex there is
   * one tab stop, so the strip's far pills are only reachable through the arrows.
   */
  const onTabListKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End')
      return
    const nodes = Array.from(barRef.current?.querySelectorAll<HTMLElement>('[role="tab"]') ?? [])
    if (nodes.length === 0) return
    const current = nodes.indexOf(e.target as HTMLElement)
    if (current < 0) return
    e.preventDefault()
    e.stopPropagation()
    const next =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? nodes.length - 1
          : (current + (e.key === 'ArrowRight' ? 1 : -1) + nodes.length) % nodes.length
    const key = tabs[next]
    if (key) onSelect(key)
    nodes[next]?.focus()
  }

  /** ArrowDown on the trigger opens the menu (P4 finding 2) — the button is a menu
   *  trigger, not a pill in the toolbar row. */
  const onTriggerKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== 'ArrowDown' || menuOpen) return
    e.preventDefault()
    e.stopPropagation()
    onToggleMenu()
  }

  return (
    // R2-P1/P2: one row that scrolls the strip of pills instead of wrapping — the
    // wrap cost up to 57 px of pane height and threw the right-hand buttons down to
    // the bottom left. @container, because the pane's width is not the window's
    // width (a max-lg: breakpoint lied about both).
    <div className="@container relative flex flex-nowrap items-center gap-1 px-2 min-h-11 py-1 border-b border-hairline flex-shrink-0">
      <button
        type="button"
        onClick={onCollapse}
        data-testid="panel-collapse-pane"
        aria-label={t('agentPanel.collapsePane')}
        title={t('agentPanel.collapsePane')}
        className={BUTTON_CLASS}
      >
        <ChevronDown className="h-4 w-4" />
      </button>
      <div
        ref={barRef}
        role="tablist"
        aria-label={t('agentPanel.title')}
        onKeyDown={onTabListKeyDown}
        className="flex min-w-0 flex-nowrap items-center gap-1 overflow-x-auto"
      >
        {tabs.map((key, index) => (
          <TabPill
            key={key}
            tabKey={key}
            active={active === key}
            focusable={tabbable === key}
            icon={<TabIcon tab={key} />}
            label={labels[key]}
            position={pillPositionDigit(index, tabs.length)}
            tipBody={tip(key).body}
            onSelect={() => onSelect(key)}
            onClose={() => {
              restoreFocus.current = true
              onCloseTab(key)
            }}
            closeLabel={t('agentPanel.closeTab')}
            tip={tip(key)}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={onToggleMenu}
        onKeyDown={onTriggerKeyDown}
        data-testid="panel-add-tab"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        // Only while open does the reference point at an existing menu —
        // otherwise a dangling aria-controls hangs in the accessibility tree.
        aria-controls={menuOpen ? 'panel-add-menu' : undefined}
        aria-label={t('agentPanel.addTab')}
        title={t('agentPanel.addTab')}
        className={BUTTON_CLASS}
      >
        <Plus className="h-4 w-4" />
      </button>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onCycleWidth}
          aria-label={t('agentPanel.cycleWidth')}
          title={t('agentPanel.cycleWidth')}
          className={BUTTON_CLASS}
        >
          <Maximize2 className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onToggleDock}
          aria-label={t('agentPanel.toggleDock')}
          title={t('agentPanel.toggleDock')}
          className={BUTTON_CLASS}
        >
          {dock === 'right' ? (
            <PanelLeftClose className="h-4 w-4" />
          ) : (
            <PanelRightClose className="h-4 w-4" />
          )}
        </button>
        <button
          type="button"
          onClick={onCollapse}
          aria-label={t('agentPanel.close')}
          className={BUTTON_CLASS}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
