'use client'

/**
 * The mark as a real node in the tree, not as an image.
 *
 * `.ephe-mark` addresses the SVG's children for the condensation
 * (`app/src/styles/globals.css`, rule `condense :is(svg > *, …)`). An `<img>` has
 * no children — the mark's signature motion would be declared and never visible.
 * The source lives in `app/src/assets/mark.svg`, and the generator and the icon
 * kit both write it from the same function: one source, no hand-maintained copy.
 *
 * The gradient ids are rewritten per instance. Two marks on one page would
 * otherwise emit the same ids twice, and the second would simply be black with no
 * gradient.
 */
import { useId } from 'react'
import type { CSSProperties } from 'react'
import markSource from '@/assets/mark.svg?raw'

export type MarkState = 'condense' | 'settle' | 'work' | 'dissolve'

export function EpheMark({
  state = 'settle',
  size = '1.5rem',
  compact = false,
  className = '',
  testId = 'ephe-mark',
}: {
  state?: MarkState
  /** A CSS length; the mark scales through `--ephe-mark-size`, not through classes. */
  size?: string
  /** 33-47 px (the compact band of MARK_CUTS): no edge light, because there the
   * band collapses into a line. */
  compact?: boolean
  className?: string
  testId?: string
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')
  const html = markSource.replace(/(mkf[a-z]+)/g, `$1${uid}`)
  return (
    <span
      data-testid={testId}
      data-state={state}
      data-size={compact ? 'compact' : undefined}
      aria-hidden="true"
      className={`ephe-mark ${className}`}
      style={{ '--ephe-mark-size': size } as CSSProperties}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
