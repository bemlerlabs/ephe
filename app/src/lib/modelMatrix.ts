/**
 * G1: one row per model, and the row says whether this machine can hold it.
 *
 * The estimate is a heuristic and says so: parameter count from the identifier,
 * bytes per weight from the quantisation suffix, plus a fifth for the KV cache
 * and the runtime. It never prints a percentage without a real total, and it
 * never guesses a name into a size.
 */
export interface ModelLike {
  id: string
}

export type FitVerdict = 'optimal' | 'tight' | 'swap'

export interface HardwareFit {
  /** Estimated resident size in GB. */
  gb: number
  /** Share of the given budget, 0–100. */
  percent: number
  verdict: FitVerdict
}

/** First occurrence wins: two provider entries for one id are one model. */
export function deduplicateEngineModels<T extends ModelLike>(models: readonly T[]): T[] {
  const seen = new Set<string>()
  const out: T[] = []
  for (const model of models) {
    const id = model.id.trim().toLowerCase()
    if (!id || seen.has(id)) continue
    seen.add(id)
    out.push(model)
  }
  return out
}

const BYTES_PER_WEIGHT: Record<string, number> = {
  fp16: 2,
  q8: 1.0625,
  q5: 0.6875,
  q4: 0.5625,
}

function bytesPerWeight(identifier: string): number {
  const lower = identifier.toLowerCase()
  if (lower.includes('fp16') || lower.includes('f16')) return BYTES_PER_WEIGHT.fp16!
  if (lower.includes('q8')) return BYTES_PER_WEIGHT.q8!
  if (lower.includes('q5')) return BYTES_PER_WEIGHT.q5!
  return BYTES_PER_WEIGHT.q4!
}

/** Billions of parameters from the identifier, or null when it names none. */
export function parameterBillions(identifier: string): number | null {
  const match = /(^|[^a-z0-9])(\d+(?:\.\d+)?)b(?![a-z0-9])/i.exec(identifier)
  if (!match) return null
  const value = Number(match[2])
  return Number.isFinite(value) && value > 0 ? value : null
}

/** Estimated resident size in GB, or null when the identifier names no size. */
export function estimateModelGb(identifier: string): number | null {
  const billions = parameterBillions(identifier)
  if (billions == null) return null
  return Math.round(billions * bytesPerWeight(identifier) * 1.2 * 10) / 10
}

/**
 * Fit against a real budget. A missing size or a missing budget yields null:
 * an unknown is stated as unknown, never as "optimal".
 */
export function evaluateModelHardwareFit(
  identifier: string,
  totalGb: number | null | undefined,
): HardwareFit | null {
  const gb = estimateModelGb(identifier)
  if (gb == null || totalGb == null || totalGb <= 0) return null
  const percent = Math.round((gb / totalGb) * 100)
  const verdict: FitVerdict = percent <= 60 ? 'optimal' : percent <= 85 ? 'tight' : 'swap'
  return { gb, percent, verdict }
}
