/**
 * Ephe — the composer's @-mention list (P3 wave 2026-10-05, from ChatInput).
 *
 * Finding P3-3: the popup opened but was not keyboard-operable —
 * ArrowDown produced no highlight, Enter SENT the message (the reviewer
 * ended up with a junk session «@read»), Escape left the list open. The list
 * is a real listbox now: highlight starts at row 1, Enter/Tab inserts,
 * Escape closes (the text stays untouched — the composer itself holds
 * both, see ChatInput.handleKeyDown).
 */
import { useTranslation } from 'react-i18next'

export interface MentionItem {
  name: string
  path: string
  type: string
}

export default function ComposerMentionList({
  items,
  activeIndex,
  onPick,
}: {
  items: MentionItem[]
  activeIndex: number
  onPick: (item: MentionItem) => void
}) {
  const { t } = useTranslation()
  if (items.length === 0) return null
  return (
    <div
      className="mb-2 rounded-lg border border-hairline bg-surface overflow-hidden"
      data-testid="mention-popup"
    >
      <p className="px-2.5 pt-1.5 text-ui-xs uppercase tracking-wide text-ink-faint">
        {t('chat.mentionTitle')}
      </p>
      <div
        id="mention-listbox"
        role="listbox"
        aria-label={t('chat.mentionTitle')}
        className="max-h-[240px] overflow-y-auto overscroll-contain"
      >
        {items.map((item, i) => {
          const active = i === Math.min(activeIndex, items.length - 1)
          return (
            <button
              key={item.path}
              type="button"
              id={`mention-opt-${i}`}
              role="option"
              aria-selected={active}
              aria-current={active ? 'true' : undefined}
              tabIndex={-1}
              onClick={() => onPick(item)}
              title={item.path}
              className={`w-full text-left px-2.5 py-1.5 text-ui-xs flex items-center gap-2 transition-colors ${
                active
                  ? 'bg-brand/20 text-foreground'
                  : 'text-ink-faint hover:bg-brand/10 hover:text-foreground'
              }`}
            >
              <span className="text-brand/70 shrink-0" aria-hidden="true">
                {item.type === 'dir' ? '▸' : '•'}
              </span>
              <span className="font-mono truncate min-w-0">{item.name}</span>
              {item.type === 'dir' && (
                <span className="ml-auto shrink-0 text-ui-2xs text-ink-faint">/</span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
