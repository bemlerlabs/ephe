'use client'

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { TAB_KEYS, Tab } from './primitives'
import { TabIcon } from './tabIcon'

/** An empty state with open-cards, when every tab is closed. */
export function PanelEmptyState({
  labels,
  onOpenTab,
}: {
  labels: Record<Tab, string>
  onOpenTab: (key: Tab) => void
}) {
  const { t } = useTranslation()
  const firstCard = useRef<HTMLButtonElement>(null)
  // Closing the last pill takes the focused close button out of the DOM and drops
  // focus on <body>. Hand it to the first card so the keyboard walk continues.
  // When the pane opens with its toggle still focused, <body> is not the holder
  // and focus stays where the user left it.
  useEffect(() => {
    if (document.activeElement === document.body) firstCard.current?.focus()
  }, [])
  return (
    <div
      data-testid="panel-empty-state"
      className="flex-1 flex flex-col items-center justify-center gap-1 px-6 py-10 text-center"
    >
      <h3 className="text-ui-lg font-semibold text-foreground/90">
        {t('agentPanel.openTabTitle')}
      </h3>
      <p className="text-ui-sm text-ink-soft mb-5">{t('agentPanel.openTabHint')}</p>
      <div className="grid grid-cols-3 gap-3 w-full max-w-md">
        {TAB_KEYS.map((key, index) => (
          <button
            key={key}
            ref={index === 0 ? firstCard : undefined}
            type="button"
            data-testid={`panel-tab-card-${key}`}
            onClick={() => onOpenTab(key)}
            className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-hairline bg-surface px-3 py-6 min-h-28 text-ink-soft hover:text-foreground hover:border-brand/40 hover:bg-brand/10 transition-colors"
          >
            <span className="text-ink-soft">
              <TabIcon tab={key} />
            </span>
            <span className="text-ui-xs font-medium">{labels[key]}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
