import { Recycle } from 'lucide-react'
import { formatNumber } from '@/lib/dateLocale'
import { sessionCostUsd, formatUsd, pricingMissing } from '@/lib/cost'
import { useTranslation } from 'react-i18next'

interface CostChipsProps {
  usageTotals: Parameters<typeof sessionCostUsd>[0]
  enginePricing: Parameters<typeof sessionCostUsd>[1]
  sessionCost: number | null
  cachePercent: number | null
}

/** Wave 3 (cost monitor + prompt-cache chip): session USD next to the token
 *  count and the measured cache share — a chip stays off when its value is
 *  missing (never guess a number). */
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

      {/* F1: the engine carries no price. Silence here read as "$0.00" from the chip
          beside it, so the absence is said out loud once — as the missing setting
          itself (i18n: statusBar.noPricing), while the title names the mechanism
          (engine.json: in_per_m/out_per_m).
          QD-015 V1: this sentence is the widest, least urgent item in the row. It
          moved behind lg and truncates, so it can no longer push the free-token
          figure into a second line while the right panel is open. */}
      {sessionCost === null && pricingMissing(usageTotals, enginePricing) && (
        <span
          data-testid="statusbar-no-pricing"
          className="hidden lg:inline-block min-w-0 max-w-[11rem] truncate text-ui-xs font-mono text-ink-faint whitespace-nowrap shrink-0"
          title={t('statusBar.noPricingTitle')}
        >
          {t('statusBar.noPricing')}
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
