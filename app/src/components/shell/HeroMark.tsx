'use client'

/**
 * S3 — the mark where the brand contract puts it above 48 px.
 *
 * `docs/PAPER_MOTH_DECISION.md` splits the figure by size: the vector rig carries the
 * small cuts, and from 48 px the slots carry the rendered actor. Two in-app slots sit at
 * exactly that size — the setup card mark (3rem) and the welcome hero fallback (4rem) —
 * and both use the shipped render (`paper-moth-actor.webp`), unpainted and unre-drawn,
 * while every sub-48 px mark stays vector.
 *
 * The render is a cut-out: measured on the committed file, 72 % of its pixels are
 * transparent and the matte fades to nothing at the edge. On paper that reads as a box,
 * which is the finding THEME_SWEEP D0-5 records for the companion. So the figure keeps
 * its own ground in both themes — the being's darkest tone, `--color-figure-head-shadow`,
 * a figure token that holds on paper by design.
 */
import type { CSSProperties } from 'react'
import './HeroMark.css'

export function HeroMark({
  size = '3rem',
  className = '',
  testId = 'hero-mark',
}: {
  /** A CSS length; the figure scales through `--hero-mark-size`, like the vector mark. */
  size?: string
  className?: string
  testId?: string
}) {
  return (
    <span
      data-testid={testId}
      aria-hidden="true"
      className={`hero-mark ${className}`}
      style={{ '--hero-mark-size': size } as CSSProperties}
    >
      <img src="/onboarding/paper-moth-actor.webp" alt="" draggable={false} />
    </span>
  )
}
