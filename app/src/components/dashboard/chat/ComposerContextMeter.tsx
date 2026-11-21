import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'

/**
 * F3: how much of the window is spent, in numbers, with the action that frees
 * it. The ring on the send button answers "roughly how full"; this answers
 * "how full, and what do I do about it".
 *
 * Since the 2026-11 quieting it is opt-in: the composer's thinking control opens
 * one discreet line carrying these numbers and /compact, so the text keeps the row.
 */
export default function ComposerContextMeter({
  percent,
  used,
  window,
  onCompact,
}: {
  percent: number | null
  used: number | null
  window: number | null
  onCompact: () => void
}) {
  const { t, i18n } = useTranslation()
  if (percent == null || used == null || window == null) return null
  const numbers = t('chat.contextMeter', {
    percent: formatNumber(Math.round(percent), i18n.language),
    used: formatNumber(used, i18n.language),
    window: formatNumber(window, i18n.language),
  })
  return (
    <span
      data-testid="composer-context-meter"
      className="tabular font-mono-code inline-flex items-center gap-1 text-ui-xs text-ink-soft shrink-0"
    >
      <span data-testid="composer-context-numbers">{numbers}</span>
      <button
        type="button"
        data-testid="composer-compact"
        onClick={onCompact}
        title={t('chat.compactNow')}
        aria-label={t('chat.compactNow')}
        className="rounded px-1 text-brand hover:bg-brand/10 transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        /compact
      </button>
    </span>
  )
}
