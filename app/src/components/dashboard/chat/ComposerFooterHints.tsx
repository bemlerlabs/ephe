import { CornerDownLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/**
 * P3-8: the composer's footer hints — recall counter (only WHILE browsing,
 * with tooltip and full name) and the queue hint. Extracted from ChatInput.tsx.
 */
export default function ComposerFooterHints({
  recall,
  queueCount,
}: {
  recall: { pos: number; total: number }
  queueCount: number
}) {
  const { t } = useTranslation()
  if (!(recall.pos > 0 || queueCount > 0)) return null
  return (
    <div className="flex items-center justify-center gap-2 mt-1 text-ui-xs text-ink-faint font-mono">
      {/* P3-8: the counter used to appear even at rest («↑/↓ 0/1») and, without
          any explanation, was pure noise. It now shows only WHILE browsing —
          with a tooltip and the full name. */}
      {recall.pos > 0 && (
        <span
          data-testid="composer-recall-counter"
          role="status"
          title={t('chat.recallHint', {
            defaultValue: '↑/↓ scrolls through your sent messages',
          })}
          aria-label={t('chat.recallAria', {
            defaultValue: 'History: position {{pos}} of {{total}}',
            pos: recall.pos,
            total: recall.total,
          })}
          className="text-ink-soft flex items-center gap-1"
        >
          <kbd className="rounded border border-hairline px-1 text-ui-2xs">↑/↓</kbd>
          {recall.pos}/{recall.total}
        </span>
      )}
      {queueCount > 0 && (
        <span
          data-testid="composer-queue-hint"
          role="status"
          className="text-brand/70 flex items-center gap-1"
        >
          <CornerDownLeft className="h-[0.875em] w-[0.875em]" aria-hidden="true" />
          {t('chat.queueHint', { count: queueCount })}
        </span>
      )}
    </div>
  )
}
