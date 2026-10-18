/**
 * The companion in the active chat: the bee (or the spark) that outlives the
 * onboarding. It sits above the composer, moves toward the answer while the
 * engine works, and loops once when it is clicked.
 *
 * All five companion settings are read here. `welcome_only` retires it as soon
 * as the chat has messages; the welcome screen owns the empty state, so this
 * surface never doubles the figure there.
 */
import './Companion.css'
import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { useDeepBool, useDeepNumber, useDeepSelect } from '@/lib/deepSettings'
import { CompanionActor, type CompanionHandle, type CompanionSpecies } from './CompanionActor'

const SPECIES: CompanionSpecies[] = ['fire_bee', 'ember_spark', 'minimal']

export default function WorkspaceCompanion({
  isStreaming,
  hasMessages,
}: {
  isStreaming: boolean
  hasMessages: boolean
}) {
  const enabled = useDeepBool('appearance.companion_enabled', true)
  const species = useDeepSelect('appearance.companion_species', 'fire_bee')
  const behavior = useDeepSelect('appearance.companion_behavior', 'interactive')
  const scale = useDeepNumber('appearance.companion_scale', 100)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const reduced = useReducedMotion()
  const still = Boolean(reduced) || !animationsEnabled
  const actor = useRef<CompanionHandle>(null)
  const loopTimer = useRef(0)
  const [looping, setLooping] = useState(false)

  useEffect(() => () => window.clearTimeout(loopTimer.current), [])

  if (!enabled || !hasMessages || behavior === 'welcome_only') return null

  const form = SPECIES.includes(species as CompanionSpecies)
    ? (species as CompanionSpecies)
    : 'fire_bee'
  const interact = behavior === 'interactive'

  return (
    <div
      data-testid="workspace-companion"
      data-behavior={behavior}
      data-species={form}
      className={`workspace-companion is-${interact ? 'interactive' : 'perch'}${
        isStreaming ? ' is-streaming' : ''
      }${looping ? ' is-looping' : ''}`}
    >
      <CompanionActor
        ref={actor}
        species={form}
        scale={scale}
        still={still}
        flying={isStreaming}
        size="workspace"
        onActivate={() => {
          actor.current?.turnTo(14)
          actor.current?.burst()
          setLooping(true)
          window.clearTimeout(loopTimer.current)
          loopTimer.current = window.setTimeout(() => setLooping(false), 1050)
        }}
      />
    </div>
  )
}
