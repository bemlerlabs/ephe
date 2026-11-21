'use client'

/**
 * The fire spirit as a real node in the tree, not an image.
 *
 * `.ephe-spirit` addresses the SVG's children from the sheet, so the states can move
 * parts of the figure; an `<img>` has no children. Both registers are in the DOM
 * together, because the first-run scene crossfades them at the turn — the threat read
 * becomes the trust read — and a crossfade needs both sides present. Only the active
 * frame paints (`opacity`), so the inactive one costs nothing per frame.
 *
 * The ids are rewritten per instance and per register. Two figures on one page would
 * otherwise emit the same ids twice and the second would draw black with no gradient;
 * the register is part of the prefix because both frames of one scene are on the page
 * at the same moment.
 */
import { useId } from 'react'
import type { CSSProperties } from 'react'
import calmSource from '@/assets/fire-spirit-bee.svg?raw'
import fierceSource from '@/assets/fire-spirit-bee-fierce.svg?raw'

/** Calm is the settled, even read; fierce is the surge — the two poles of the arc. */
export type SpiritRegister = 'calm' | 'fierce'

/** What the figure is doing. The sheet turns each state into motion. */
export type SpiritState = 'rest' | 'land' | 'hold' | 'lean' | 'lead' | 'flight' | 'ember'

const FRAMES: { register: SpiritRegister; source: string; prefix: string }[] = [
  { register: 'calm', source: calmSource, prefix: 'bspc' },
  { register: 'fierce', source: fierceSource, prefix: 'bspf' },
]

export function FireSpirit({
  register = 'calm',
  state = 'rest',
  size = '6rem',
  className = '',
  testId = 'fire-spirit',
}: {
  register?: SpiritRegister
  state?: SpiritState
  /** A CSS length; the figure scales through `--ephe-spirit-size`. */
  size?: string
  className?: string
  testId?: string
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')
  return (
    <span
      data-testid={testId}
      data-state={state}
      data-register={register}
      aria-hidden="true"
      className={`ephe-spirit ${className}`}
      style={{ '--ephe-spirit-size': size } as CSSProperties}
    >
      {FRAMES.map((frame) => (
        <span
          key={frame.register}
          data-frame={frame.register}
          className="ephe-spirit-frame"
          dangerouslySetInnerHTML={{
            __html: frame.source.replace(
              new RegExp(`${frame.prefix}-`, 'g'),
              `${frame.prefix}${uid}-`,
            ),
          }}
        />
      ))}
    </span>
  )
}
