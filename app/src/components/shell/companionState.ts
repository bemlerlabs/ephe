import type { RunState } from './AgenticBar'

/** What the actor does with the one run state the bar shows. */
export type CompanionMood = 'rest' | 'moving' | 'still' | 'settle'

export function companionMood(state: RunState): CompanionMood {
  if (state === 'working') return 'moving'
  if (state === 'waiting') return 'still'
  if (state === 'done') return 'settle'
  return 'rest'
}
