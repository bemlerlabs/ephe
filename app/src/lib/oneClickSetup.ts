/**
 * P2: the one-click offer behind the first-run button.
 *
 * It answers one question from evidence the scan already produced: which engine
 * on this machine answered, and which of its models fits the memory the endpoint
 * reported. It never invents an address, never picks an engine the scan did not
 * reach, and never picks a keyed service — a click cannot supply the key, so a
 * cloud endpoint stays a deliberate row below.
 */
import type { DetectedEngine } from './api/providers'
import { evaluateModelHardwareFit, type HardwareFit } from './modelMatrix'

export type OneClickKind = 'local_ollama' | 'custom_ollama'

export interface OneClickChoice {
  kind: OneClickKind
  /** The endpoint that answered; empty means the loopback default. */
  url: string
  model: string
  /** Null when neither the name nor the memory states a size. */
  fit: HardwareFit | null
  /** 'local' = this machine's Ollama; 'own' = an endpoint the user already runs. */
  basis: 'local' | 'own'
}

/** This machine's Ollama first (offline, no credentials), then an endpoint the user
 *  already keeps in engine.json or on the LAN. */
const ORDER: OneClickKind[] = ['local_ollama', 'custom_ollama']

function pickModel(models: readonly string[], totalGb: number | null): {
  model: string
  fit: HardwareFit | null
} | null {
  const sized = models
    .map((id) => ({ id, fit: evaluateModelHardwareFit(id, totalGb) }))
    .filter((entry): entry is { id: string; fit: HardwareFit } => entry.fit != null)
  if (sized.length === 0) {
    // No size anywhere: the engine's own first entry, stated as unknown.
    return models[0] ? { model: models[0], fit: null } : null
  }
  const optimal = sized.filter((entry) => entry.fit.verdict === 'optimal')
  if (optimal.length > 0) {
    const largest = optimal.reduce((a, b) => (b.fit.gb > a.fit.gb ? b : a))
    return { model: largest.id, fit: largest.fit }
  }
  const tight = sized.filter((entry) => entry.fit.verdict === 'tight')
  if (tight.length > 0) {
    const smallest = tight.reduce((a, b) => (b.fit.gb < a.fit.gb ? b : a))
    return { model: smallest.id, fit: smallest.fit }
  }
  // Every sized model would swap: recommending one would recommend the swap.
  return null
}

export function recommendOneClickSetup(
  detected: readonly DetectedEngine[],
  totalGb: number | null,
): OneClickChoice | null {
  const usable = detected.filter(
    (engine) =>
      ORDER.includes(engine.provider as OneClickKind) &&
      engine.reachable &&
      engine.models.length > 0 &&
      // A probe answered with a key found beside Ephe would not answer the chat.
      engine.key_source !== 'foreign',
  )
  for (const kind of ORDER) {
    for (const engine of usable.filter((item) => item.provider === kind)) {
      const pick = pickModel(engine.models, totalGb)
      if (!pick) continue
      return {
        kind,
        url: engine.url ?? '',
        model: pick.model,
        fit: pick.fit,
        basis: kind === 'local_ollama' ? 'local' : 'own',
      }
    }
  }
  return null
}
