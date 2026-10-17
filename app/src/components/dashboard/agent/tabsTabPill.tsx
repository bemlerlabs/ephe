'use client'

import { X } from 'lucide-react'
import SmartTip from '../SmartTip'
import { Tab } from './primitives'
import { isMacPlatform } from '@/lib/shortcuts'

/**
 * DOM ids of the tab relationship — the pill is the trigger, the panel
 * (panel.tsx) the target node. Both sides read the same helper so that
 * aria-controls and aria-labelledby cannot drift apart
 * (R2 §4.4: "tab metadata is missing across the whole panel").
 */
export const agentTabDomIds = {
  tab: (key: Tab) => `agent-panel-tab-${key}`,
  panel: (key: Tab) => `agent-panel-tabpanel-${key}`,
}

/** ⌘1–⌘9 (Mac) and Strg1–Strg9 address the position in the VISIBLE
 *  bar (P4 finding 3, binding: useTabRegistry). Digit 10 is ⌘0. */
export function pillShortcut(position: number | null): { label: string; aria: string } | null {
  if (position === null) return null
  const digit = position === 0 ? '0' : String(position)
  const mac = isMacPlatform()
  return {
    label: mac ? `⌘${digit}` : `Strg${digit}`,
    aria: `${mac ? 'Meta' : 'Control'}+${digit}`,
  }
}

/**
 * Round G: the tab pill (reference pattern) — a click activates it, the close-X
 * removes the page from the inventory (restorable through the + menu).
 *
 * R2 §4.4 point 3: the role no longer sits on a wrapping `div` that carries a
 * focusable `button` as its child (an invalid structure) but on the clickable
 * element itself — a `button[role=tab]`. The close button is its sibling, not its
 * child (no nested interactive content). Roving tabindex: only the active pill is
 * tabbable; the arrow keys move the selection (panelTabBar). Enter/Space is
 * handled by the `button` itself.
 *
 * P4 finding 4: the title was a bare repeat of the label. Now it is
 * "Evidence — the chain of what really ran … (⌘2)": the label, the content
 * expectation from the real tooltip text, and the digit this pill actually
 * selects. The shortcut additionally sits in the accessibility tree as
 * aria-keyshortcuts so a screen reader announces it.
 */
export function TabPill({
  tabKey,
  active,
  focusable = active,
  icon,
  label,
  position = null,
  tipBody,
  onSelect,
  onClose,
  closeLabel,
  tip,
}: {
  tabKey: Tab
  active: boolean
  /** Roving tabindex: the active pill; panelTabBar fallback: the first. */
  focusable?: boolean
  icon: React.ReactNode
  label: string
  /** Position in the visible bar (1-based), 0 = ⌘0, null = no digit. */
  position?: number | null
  /** Expected content from agentPanel.tabTip*.body — without it the title stays honestly brief. */
  tipBody?: string
  onSelect: () => void
  onClose: () => void
  closeLabel: string
  tip: { title: string; body: string }
}) {
  const shortcut = pillShortcut(position)
  // Pattern (P4 finding 4): "Evidence — the chain of what really ran … (⌘2)".
  // When the locales carry no content expectation it stays "Label (⌘2)" — the
  // surface never shows an invented description.
  const title = `${label}${tipBody ? ` — ${tipBody}` : ''}${shortcut ? ` (${shortcut.label})` : ''}`
  return (
    <div
      className={`flex items-center rounded-lg shrink-0 whitespace-nowrap transition-colors max-lg:min-h-11 ${active ? 'bg-brand/20' : 'hover:bg-surface'}`}
    >
      <button
        type="button"
        role="tab"
        id={agentTabDomIds.tab(tabKey)}
        aria-selected={active}
        // Only the active pill points at a panel — exactly one panel renders, for
        // the active tab; a reference from an inactive pill would point at nothing
        // and leave a dangling aria-controls.
        aria-controls={active ? agentTabDomIds.panel(tabKey) : undefined}
        // Below lg the label is an icon only — the name stays in the a11y tree via aria-label
        aria-label={label}
        aria-keyshortcuts={shortcut?.aria}
        title={title}
        tabIndex={focusable ? 0 : -1}
        data-testid={`panel-tab-pill-${tabKey}`}
        onClick={onSelect}
        className={`flex items-center gap-1 pl-2.5 pr-1 py-1.5 min-h-7 rounded-lg text-ui-xs font-medium transition-colors cursor-pointer @max-[26rem]:min-w-11 @max-[26rem]:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ${active ? 'text-brand' : 'text-ink-soft hover:text-foreground'}`}
      >
        <SmartTip testId={`panel-tab-tip-${tabKey}`} tip={tip} side="bottom">
          <span className="flex items-center gap-1">
            {icon}
            {/* R2-P1: a viewport breakpoint lies about the width of this
                container — the pane is 420–720 px regardless of the window.
                The name only gives way when the lanes themselves get too tight. */}
            <span className="hidden @[26rem]:inline">{label}</span>
          </span>
        </SmartTip>
      </button>
      <button
        type="button"
        data-testid={`panel-tab-close-${tabKey}`}
        aria-label={closeLabel}
        // P4 finding 4: the close button names its effect on THIS pill too.
        title={`${closeLabel}: ${label}`}
        // R2 §4.4 point 4: it was p-0.5 with h-3 w-3 = a roughly 16x16 px target.
        // Now 28 px on desktop, 44 px below lg; the icon itself stays small.
        onClick={(e) => {
          e.stopPropagation()
          onClose()
        }}
        onKeyDown={(e) => e.stopPropagation()}
        className="grid place-items-center h-7 w-7 shrink-0 rounded-md text-ink-faint hover:text-foreground hover:bg-surface max-lg:h-11 max-lg:min-w-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}
