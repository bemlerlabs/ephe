/**
 * The companion in the active chat: the bee (or the spark) that outlives the
 * onboarding. It sits above the composer, moves toward the answer while the
 * engine works, and opens its quick panel on click.
 *
 * The run state is the one `runStateOf` hands the run bar — no second health
 * read and no private interval. `header` is the header perch's place; this
 * surface stays out of it.
 */
import './Companion.css'
import { useReducedMotion } from 'framer-motion'
import { useDeepBool, useDeepNumber, useDeepSelect } from '@/lib/deepSettings'
import type { RunState } from './AgenticBar'
import { CompanionQuickPanel } from './CompanionQuickPanel'
import type { CompanionSpecies } from './CompanionActor'
import { companionMood } from './companionState'

const SPECIES: CompanionSpecies[] = ['fire_bee', 'ember_spark', 'minimal']

export default function WorkspaceCompanion({
  runState,
  hasMessages,
}: {
  runState: RunState
  hasMessages: boolean
}) {
  const enabled = useDeepBool('appearance.companion_enabled', true)
  const species = useDeepSelect('appearance.companion_species', 'fire_bee')
  const behavior = useDeepSelect('appearance.companion_behavior', 'interactive')
  const scale = useDeepNumber('appearance.companion_scale', 100)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const reduced = useReducedMotion()
  const mood = companionMood(runState)
  const still = Boolean(reduced) || !animationsEnabled || mood === 'still' || mood === 'settle'

  if (!enabled || !hasMessages || behavior === 'welcome_only' || behavior === 'header') return null

  const form = SPECIES.includes(species as CompanionSpecies)
    ? (species as CompanionSpecies)
    : 'fire_bee'
  const interact = behavior === 'interactive'

  return (
    <div
      data-testid="workspace-companion"
      data-behavior={behavior}
      data-species={form}
      data-state={runState}
      data-mood={mood}
      className={`workspace-companion is-${interact ? 'interactive' : 'perch'}${
        mood === 'moving' ? ' is-streaming' : ''
      }${mood === 'still' ? ' is-quiet' : ''}${mood === 'settle' ? ' is-settle' : ''}`}
    >
      <CompanionQuickPanel
        runState={runState}
        species={form}
        scale={scale}
        still={still}
        placement="composer"
      />
    </div>
  )
}
