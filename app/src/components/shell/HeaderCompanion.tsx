/**
 * The header perch: the same actor, at rest next to the mark. The slot keeps its
 * size before the first message, so the title never moves when the figure
 * arrives; the run state is the one the bar shows; there is no second read.
 */
import { useReducedMotion } from 'framer-motion'
import { useDeepBool, useDeepNumber, useDeepSelect } from '@/lib/deepSettings'
import type { RunState } from './AgenticBar'
import { CompanionQuickPanel } from './CompanionQuickPanel'
import type { CompanionSpecies } from './CompanionActor'
import { companionMood } from './companionState'

const SPECIES: CompanionSpecies[] = ['fire_bee', 'ember_spark', 'minimal']

export default function HeaderCompanion({
  runState,
  hasMessages,
}: {
  runState: RunState
  hasMessages: boolean
}) {
  const enabled = useDeepBool('appearance.companion_enabled', false)
  const species = useDeepSelect('appearance.companion_species', 'fire_bee')
  const behavior = useDeepSelect('appearance.companion_behavior', 'interactive')
  const scale = useDeepNumber('appearance.companion_scale', 100)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const reduced = useReducedMotion()
  const still =
    Boolean(reduced) || !animationsEnabled || (runState !== 'ready' && runState !== 'working')
  const mood = companionMood(runState)

  if (!enabled || behavior !== 'header') return null

  const form = SPECIES.includes(species as CompanionSpecies)
    ? (species as CompanionSpecies)
    : 'fire_bee'

  return (
    <div
      data-testid="header-companion-slot"
      className="header-companion-slot"
      aria-hidden={!hasMessages}
    >
      {hasMessages && (
        <div
          data-testid="header-companion"
          data-state={runState}
          data-mood={mood}
          className={`header-companion is-${mood}`}
        >
          <CompanionQuickPanel
            runState={runState}
            species={form}
            scale={scale}
            still={still}
            placement="header"
          />
        </div>
      )}
    </div>
  )
}
