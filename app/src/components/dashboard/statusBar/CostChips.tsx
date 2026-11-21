import { Recycle } from 'lucide-react'
import { formatNumber } from '@/lib/dateLocale'
import { sessionCostUsd, formatUsd } from '@/lib/cost'
import { useTranslation } from 'react-i18next'

interface CostChipsProps {
  usageTotals: Parameters<typeof sessionCostUsd>[0]
  enginePricing: Parameters<typeof sessionCostUsd>[1]
  sessionCost: number | null
  cachePercent: number | null
}

/** Wave 3 (cost monitor + prompt-cache chip): session USD next to the token
 *  count and the measured cache share — a chip stays off when its value is
 *  missing (never guess a number). The row states no missing-price claim: a
 *  quiet cost chip is the absence, and the agent-status panel's usage section
 *  names the missing setting (owner decision 2026-11-15). */
export function CostChips({
  usageTotals,
  enginePricing,
  sessionCost,
  cachePercent,
}: CostChipsProps) {
  const { t, i18n } = useTranslation()
  return (
    <>
      {/* Wave 3 (cost monitor): session USD next to the token count —
          only when engine.json maintains `pricing` and usage was measured. */}
      {sessionCost !== null && (
        <span
          data-testid="statusbar-cost"
          className="min-w-0 max-w-[7rem] truncate text-ui-xs font-mono tabular-nums text-brand/80 whitespace-nowrap shrink-0"
          title={t('statusBar.costTitle', {
            in: formatNumber(usageTotals?.in ?? 0, i18n.language),
            out: formatNumber(usageTotals?.out ?? 0, i18n.language),
            inPerM: enginePricing?.in_per_m ?? 0,
            outPerM: enginePricing?.out_per_m ?? 0,
          })}
        >
          {formatUsd(sessionCost)}
        </span>
      )}

      {/* Wave 3 (prompt-cache chip): measured cache share of the prompt tokens.
          The mark was a literal zap emoji, sized and baseline-shifted by the platform, and
          the only chip in the row drawn outside the icon set. Cache is reuse rather than
          speed, and the row already spends a zap on the token count and on the rate. */}
      {cachePercent !== null && (
        <span
          data-testid="statusbar-cache"
          className="hidden lg:inline-flex items-center gap-1 text-ui-xs font-mono tabular-nums text-brand/80 whitespace-nowrap shrink-0"
          title={t('statusBar.cacheTitle', { percent: cachePercent })}
          aria-label={t('statusBar.cacheTitle', { percent: cachePercent })}
        >
          <Recycle className="h-3.5 w-3.5 text-brand/70" />
          {cachePercent}%
        </span>
      )}
    </>
  )
}
