import type { ContextBudget } from '@/lib/api'
import { formatNumber } from '@/lib/dateLocale'

/** Where the window comes from — the surface has to say so.
 *
 * The number is formatted with the language of the surface, not with `String`
 * or a bare toLocaleString(): a bare call takes the separator from the operating
 * system, so an English interface on a German machine printed „262.144".
 *
 * The active engine does not name its window (measured on 2026-10-08 against
 * /v1/models: id, object, owned_by — nothing else). Then 8.192 stays as the
 * computed value for the cap, but it is **not** that machine's window, and a
 * meter showing 57 % against an assumed window without saying so is a number
 * that looks like a measurement. */
export function windowHint(
  budget: ContextBudget | null,
  windowSize: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
  language: string | undefined,
): string {
  if (!budget) return t('statusBar.contextMeterHint')
  const figures = formatNumber(windowSize, language)
  switch (budget.window_source) {
    case 'engine':
      return t('statusBar.windowEngine', { window: figures })
    case 'tier':
      return t('statusBar.windowTier', { window: figures })
    case 'env':
      return t('statusBar.windowSetting', { window: figures })
    default:
      return t('statusBar.windowAssumed', { window: figures })
  }
}
