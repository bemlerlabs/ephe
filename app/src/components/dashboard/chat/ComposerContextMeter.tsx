import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'

/**
 * F3: how much of the window is spent, in numbers, with the action that frees
 * it. The ring on the send button answers "roughly how full"; this answers
 * "how full, and what do I do about it".
 *
 * Hidden below md: the 390 px action row is spent on the controls a new turn
 * needs, and /compact stays reachable through the slash menu there.
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
  // One thousandth of a window is not zero: below one percent the round number
  // reads as "nothing used" while tokens are plainly there.
  const shown = percent > 0 && percent < 1 ? '<1' : formatNumber(Math.round(percent), i18n.language)
  const numbers = t('chat.contextMeter', {
    percent: shown,
    used: formatNumber(used, i18n.language),
    window: formatNumber(window, i18n.language),
  })
  return (
    <span
      data-testid="composer-context-meter"
      className="tabular font-mono-code inline-flex items-center gap-1 text-ui-xs text-ink-soft shrink-0 max-md:hidden"
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
