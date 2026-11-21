'use client'

/**
 * The paper moth as a living thing: five states, one figure.
 *
 * The wings are the two cut halves of the master and the body is its own strip, so a
 * flap turns real paper planes on the perspective of the stage instead of scaling a
 * photograph. Every state is CSS on `data-state`, so a state change costs one
 * attribute and a reduced-motion reader gets the still figure.
 *
 * States: `ready` (a breath of air every ten seconds), `working` (the slow flap and
 * the light that walks the fibres), `waiting` (the crimson ties pulse — a letter
 * waiting to be sealed), `done` (folds to the sealed slip) and `evaporated` (rises
 * out of frame, leaving the document behind).
 */
import { useEffect, useRef, useState } from 'react'
import { INTRO_SEEN_KEY } from '@/lib/firstRun'
import { paperRustle } from '@/lib/paperRustle'
import './PaperMoth.css'

export type MothState = 'ready' | 'working' | 'waiting' | 'done' | 'evaporated'

const UNFOLD_MS = 1800
const SEEN = 'ephe.moth.unfolded'

export function PaperMoth({
  state = 'ready',
  size = '9rem',
  unfold = false,
  className = '',
  testId = 'paper-moth',
}: {
  state?: MothState
  /** A CSS length: the stage's width and height. */
  size?: string
  /** Play the 1.8 s origami unfold — on the first start of an install. */
  unfold?: boolean
  className?: string
  testId?: string
}) {
  const [opening, setOpening] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (!unfold || typeof window === 'undefined') return
    let seen = true
    try {
      const filmSeen = window.localStorage.getItem(INTRO_SEEN_KEY) === '1'
      const mothSeen = window.localStorage.getItem(SEEN) === '1'
      window.localStorage.setItem(SEEN, '1')
      seen = mothSeen || !filmSeen
    } catch {
      seen = true
    }
    if (seen) return
    setOpening(true)
    paperRustle()
    timer.current = window.setTimeout(() => setOpening(false), UNFOLD_MS)
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [unfold])

  return (
    <span
      data-testid={testId}
      data-state={state}
      data-unfold={opening ? 'true' : undefined}
      aria-hidden="true"
      className={`paper-moth ${className}`}
      style={{ ['--moth-size' as string]: size }}
    >
      <span className="paper-moth-stage">
        <img className="paper-moth-wing is-left" src="/onboarding/paper-moth-wing-l.webp" alt="" />
        <img className="paper-moth-wing is-right" src="/onboarding/paper-moth-wing-r.webp" alt="" />
        <img className="paper-moth-body" src="/onboarding/paper-moth-body.webp" alt="" />
        <span className="paper-moth-thread">
          <i className="knot is-left" />
          <i className="knot is-right" />
        </span>
        <span className="paper-moth-sheen" />
      </span>
    </span>
  )
}
