/**
 * The engine's condition, in one place.
 *
 * The welcome screen, the composer chip and the run bar used to derive the same
 * condition from three different reads. This first cut names the condition from
 * the health answer; the gate and the chat poll feed the same function as the
 * next slice. A reachable engine with a model is ready; a reachable one without a
 * model is not, because the user has one more choice to make.
 */
import type { HealthInfo } from '@/lib/api'

export type EngineState =
  'checking' | 'unconfigured' | 'unreachable' | 'key-refused' | 'no-model' | 'ready'

/** The state one health answer supports. `null` means the answer has not landed. */
export function engineStateOf(health: HealthInfo | null): EngineState {
  if (!health) return 'checking'
  if (health.engine_key_challenge) return 'key-refused'
  if (health.engine_state === 'unreachable' || health.engine_online === false) return 'unreachable'
  if (!health.active_model) return 'no-model'
  return 'ready'
}
