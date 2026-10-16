/**
 * Ephe — wave 3 (cost monitor & prompt-cache chip).
 *
 * Working-backwards finding from the cockpit comparison (2026-10): users of
 * desktop agent clients expect USD next to the token count and a cache-first
 * indicator. Ephe computes BOTH only from measured values:
 *
 *  - Cost: engine.json `pricing` ({"in_per_m": USD/1M, "out_per_m": USD/1M})
 *    × the accumulated session sums from the usage frames. No price maintained
 *    → null → the UI shows nothing (never guess a number).
 *  - Cache: measured prompt_tokens_details.cached_tokens / prompt_tokens.
 *    Without measured cache fields → null → no chip.
 */

export interface EnginePricing {
  in_per_m?: number
  out_per_m?: number
}

export interface UsageTotals {
  in: number
  out: number
  cached: number
}

/** USD cost of the session; null when there is no price and/or no usage. */
export function sessionCostUsd(
  totals: UsageTotals | null | undefined,
  pricing: EnginePricing | null | undefined,
): number | null {
  if (!totals || !pricing) return null
  const inPerM = pricing.in_per_m
  const outPerM = pricing.out_per_m
  if (typeof inPerM !== 'number' && typeof outPerM !== 'number') return null
  const inTok = totals.in || 0
  const outTok = totals.out || 0
  if (inTok === 0 && outTok === 0) return null
  const cost = (inTok / 1_000_000) * (inPerM ?? 0) + (outTok / 1_000_000) * (outPerM ?? 0)
  return cost
}

/** Display form: micro-amounts with 4 decimals, otherwise 2 ("$0.0012" / "$1.24"). */
export function formatUsd(cost: number): string {
  if (cost > 0 && cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}

/**
 * Tokens were measured and the engine carries no price to multiply them by. That is
 * a fact the row can state (F1): the cost chip going quiet is the same shape as a
 * chip reading zero, and the reader cannot tell the two apart from the row.
 */
export function pricingMissing(
  totals: UsageTotals | null | undefined,
  pricing: EnginePricing | null | undefined,
): boolean {
  const measured = (totals?.in ?? 0) + (totals?.out ?? 0) > 0
  const priced = typeof pricing?.in_per_m === 'number' || typeof pricing?.out_per_m === 'number'
  return measured && !priced
}

/** Share of cached prompt tokens in percent (rounded); null without a measurement. */
export function cacheSharePercent(
  totals: UsageTotals | null | undefined,
  lastTurn: { in: number; cached?: number } | null | undefined,
): number | null {
  // Prefers the last turn (current cache effectiveness), otherwise the totals.
  const source =
    lastTurn && lastTurn.in > 0
      ? { in: lastTurn.in, cached: lastTurn.cached ?? 0 }
      : totals && totals.in > 0
        ? { in: totals.in, cached: totals.cached }
        : null
  if (!source || source.cached <= 0) return null
  return Math.round((source.cached / source.in) * 100)
}
