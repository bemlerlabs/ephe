/**
 * P1: one proof, two readers. The everyday reader is told that the check held;
 * the expert reader is told what ran, for how long and with which result. The
 * mode is the existing `chat.details_mode`, so the disclosure switch and the
 * wording switch are the same switch, not two settings that can disagree.
 */
export type Audience = 'everyday' | 'expert'

/** collapsed = everyday, expanded = expert; anything unknown reads as everyday. */
export function audienceOf(detailsMode: string | null | undefined): Audience {
  return detailsMode === 'expanded' ? 'expert' : 'everyday'
}

export interface ProofFacts {
  ok: boolean
  /** Summed run time of the group, when the stream reported one. */
  ms?: number | null
}

export interface ProofText {
  key: string
  values?: Record<string, string | number>
}

/** The sentence for a finished tool group, per audience. */
export function proofText(audience: Audience, facts: ProofFacts): ProofText {
  if (!facts.ok) return { key: 'chat.proof.failed' }
  const ms = facts.ms != null && facts.ms > 0 ? Math.round(facts.ms) : null
  if (audience === 'expert') {
    return ms == null ? { key: 'chat.proof.expertNoTime' } : { key: 'chat.proof.expert', values: { ms } }
  }
  if (ms == null) return { key: 'chat.proof.everydayNoTime' }
  return { key: 'chat.proof.everyday', values: { seconds: (ms / 1000).toFixed(1) } }
}
