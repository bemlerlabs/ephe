import { formatNumber, formatRate } from '@/lib/dateLocale'

/**
 * The ring's one sentence: how full the context window is. The arc itself is
 * `aria-hidden`, so without a name on its wrapper the number exists only for
 * someone who can hover — which rules out every touch device.
 */
export function contextRingLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  percent: number | null | undefined,
  language?: string,
): string {
  const p = percent ?? 0
  return t('chat.contextRing', {
    percent: p < 10 ? formatRate(p, language) : formatNumber(Math.round(p), language),
  })
}
