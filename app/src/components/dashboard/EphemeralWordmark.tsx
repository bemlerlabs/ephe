/**
 * Ephe — EphemeralWordmark: the brand name with a fading dot trail.
 *
 * The trail dots breathe (opacity) like the decaying half of the emblem
 * ("Fading Circle") — the brand moment in the chat empty state, deliberately small.
 * Reduced Motion holds the dots static (CSS media query + play state).
 * The text stays ONE text node so textContent pins (hero-brand)
 * keep matching; the dots carry no text.
 */
import { useReducedMotion } from 'framer-motion'

const DOTS = [
  { em: 0.375, opacity: 0.85, delay: 0 },
  { em: 0.3, opacity: 0.6, delay: 0.4 },
  { em: 0.24, opacity: 0.42, delay: 0.8 },
  { em: 0.19, opacity: 0.24, delay: 1.2 },
] as const

export default function EphemeralWordmark({
  text,
  className = '',
}: {
  text: string
  className?: string
}) {
  const reduceMotion = useReducedMotion()
  return (
    <span
      data-testid="ephemeral-wordmark"
      className={`inline-flex items-baseline gap-[0.28em] ${className}`}
    >
      <span>{text}</span>
      <span
        aria-hidden="true"
        className="inline-flex items-baseline gap-[0.13em] -translate-y-[0.06em]"
      >
        {DOTS.map((d, i) => (
          <span
            key={i}
            data-testid={`ephemeral-dot-${i}`}
            className="ephemeral-dot inline-block rounded-full bg-brand"
            style={{
              width: `${d.em}em`,
              height: `${d.em}em`,
              ['--dot-op' as string]: d.opacity,
              animationDelay: `${d.delay}s`,
              animationPlayState: reduceMotion ? 'paused' : undefined,
            }}
          />
        ))}
      </span>
    </span>
  )
}
