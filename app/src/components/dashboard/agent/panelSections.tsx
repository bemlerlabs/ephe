'use client'

import { useTranslation } from 'react-i18next'
import { TabIcon } from './tabIcon'
import { SECTION_LEAD, type Section } from './workbenchModel'

const BUTTON_CLASS =
  'inline-flex items-center gap-1.5 px-2 py-1 min-h-7 rounded-md text-ui-xs transition-colors ' +
  'focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ' +
  '@max-[26rem]:min-h-11'

/**
 * C1: the section row. One icon per section that holds something open, and the
 * icon of the section already forward is the handle that folds the body away —
 * the same control that opened it, so the gesture is one thing, not two.
 */
export function PanelSections({
  sections,
  counts,
  forward,
  collapsed,
  onToggle,
}: {
  sections: readonly Section[]
  counts: Partial<Record<Section, number>>
  forward: Section | null
  collapsed: boolean
  onToggle: (section: Section) => void
}) {
  const { t } = useTranslation()
  if (!sections.length) return null
  return (
    <div
      data-testid="panel-sections"
      role="group"
      aria-label={t('agentPanel.sectionsAria')}
      className="flex items-center gap-1 px-2 h-9 border-b border-hairline flex-shrink-0 overflow-x-auto"
    >
      {sections.map((section) => {
        const isForward = forward === section
        const open = isForward && !collapsed
        const count = counts[section] ?? 0
        return (
          <button
            key={section}
            type="button"
            data-testid={`panel-section-${section}`}
            aria-pressed={open}
            aria-label={t(`agentPanel.section.${section}`)}
            title={t(`agentPanel.section.${section}`)}
            onClick={() => onToggle(section)}
            className={`${BUTTON_CLASS} ${
              open
                ? 'bg-brand/10 text-foreground'
                : 'text-ink-soft hover:bg-surface hover:text-foreground'
            }`}
          >
            <TabIcon tab={SECTION_LEAD[section]} />
            {/* Minimal until it is the one you are looking at: a row of five words
                is the flat bar again. The name stays on the accessible label and
                the title, so nothing is only ever an icon. */}
            {open && <span className="truncate">{t(`agentPanel.section.${section}`)}</span>}
            {count > 1 && (
              <span className="font-mono text-ui-2xs text-ink-faint" aria-hidden="true">
                {count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
