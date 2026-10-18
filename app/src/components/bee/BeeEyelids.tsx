/**
 * Two eyelids for the companion's open eyes: a blink every few seconds and a
 * wink when the caller asks. The lids are paint over the actor, so the eye
 * pixels stay untouched and the closed state takes ~140 ms.
 */
import './BeeEyelids.css'
import { useEffect, useState } from 'react'

export function BeeEyelids({
  still = false,
  winkSignal = 0,
  className = '',
}: {
  still?: boolean
  winkSignal?: number
  className?: string
}) {
  const [state, setState] = useState<'idle' | 'blink' | 'wink'>('idle')

  useEffect(() => {
    if (still) return
    let timer = 0
    let close = 0
    let alive = true
    const loop = () => {
      timer = window.setTimeout(
        () => {
          if (!alive) return
          setState(Math.random() < 0.28 ? 'wink' : 'blink')
          close = window.setTimeout(() => {
            if (alive) {
              setState('idle')
              loop()
            }
          }, 150)
        },
        3200 + Math.random() * 3600,
      )
    }
    loop()
    return () => {
      alive = false
      window.clearTimeout(timer)
      window.clearTimeout(close)
    }
  }, [still])

  useEffect(() => {
    if (still || winkSignal === 0) return
    setState('wink')
    const close = window.setTimeout(() => setState('idle'), 280)
    return () => window.clearTimeout(close)
  }, [winkSignal, still])

  return (
    <span
      className={`bee-eyelids ${state !== 'idle' ? `is-${state}` : ''} ${className}`}
      aria-hidden="true"
    >
      <i />
      <i />
    </span>
  )
}
