/**
 * The engine's own answer shapes: the three-valued state a probe or the health route
 * reports, and the per-model record a probe carries beside its id list.
 *
 * Split out of `types.ts` on 2026-10-18, when S1's nullable metadata joined the probe
 * response and the file passed the 400-line ceiling. `types.ts` keeps the store and
 * session shapes; the barrel re-exports both, so `@/lib/api` is unchanged for every
 * surface that reads them.
 */

/** Three-valued engine states from the health and probe routes. */
export type EngineState = 'ok' | 'busy' | 'unreachable'

/** An engine candidate for the parallel auto-scan (URL null => local default). */
export interface EngineCandidate {
  provider: string
  url: string | null
  /** Port hint of the loopback scan: it names what a port commonly serves, so it is
   *  never a recognition. `hint_code` is the machine half, `hint` the sentence an old
   *  client and the log read. Both come from `_ENGINE_PORTS` in
   *  server/routes/settings.py. */
  hint?: string
  hint_code?: string
  /** From this machine's loopback scan (not from engine.json/history/env).
   *  R9: the surface uses it to say WHERE a suggestion comes from, instead of
   *  calling both "recognised". */
  sweep?: boolean
}

/** Which token authenticated a probe: the one sent with the request, Ephe's own store,
 *  the onboarding mirror, or none. `foreign` is the case the setup line says out loud. */
export type ProbeKeySource = 'given' | 'own' | 'foreign' | 'none'

/** S1: what an endpoint said about one of its models. Every field is nullable and
 *  `null` means the engine never answered it — the surface shows an em-dash and the
 *  filter treats the row as unknown, so no number here is ever derived from the name. */
export interface ModelMetadata {
  /** The tag a request sends, when the record stands beside a `models` list. */
  id?: string
  name?: string | null
  context_window?: number | null
  price_in_per_m?: number | null
  price_out_per_m?: number | null
  is_free?: boolean | null
  supports_tools?: boolean | null
  supports_vision?: boolean | null
}

/** Result of a single candidate probe from /api/setup/detect. */
export interface DetectedEngine {
  provider: string
  url: string | null
  reachable: boolean
  models: string[]
  detail: string
  state?: EngineState
  /** Port hint, same pair as on the candidate. */
  hint?: string
  hint_code?: string
  key_source?: ProbeKeySource
  /** Aligned with `models`; absent for an Ollama scan, whose names carry no metadata. */
  model_details?: ModelMetadata[]
}

/** Response from GET /api/setup/detect — parallel multi-engine scan. */
export interface DetectResponse {
  candidates: EngineCandidate[]
  detected: DetectedEngine[]
  /** Index of the first reachable candidate with >= 1 model, otherwise -1. */
  first_reachable: number
}

export interface ProviderProbeResponse {
  reachable: boolean
  models: string[]
  detail: string
  /** Probed endpoint (echoed by the server; used for structured UI rendering). */
  url?: string
  /** W18/A5: ok | busy | unreachable (busy = timeout, NOT offline). */
  state?: EngineState
  /** Where the token that answered this probe came from. */
  key_source?: ProbeKeySource
  /** Aligned with `models`. An Ollama list is all-unknown, never guessed. */
  model_details?: ModelMetadata[]
}
