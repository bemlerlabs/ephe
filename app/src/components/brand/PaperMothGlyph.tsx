'use client'

import type { ReactNode } from 'react'

/**
 * The moth at 16–24 px, drawn as geometry rather than shrunk from the photograph.
 *
 * Four origami planes and a red body, on the same 96 grid the kit's vector uses, so
 * the small glyph and the large actor are the same figure. A photo loses its fibres
 * long before 24 px; this does not. The stroke is 1.5 units — the weight the top bar
 * and the tray use — and it is paint, not outline-only, because a hairline silhouette
 * disappears on a dark bar.
 */
const WINGS: Array<{ points: string; lit: boolean }> = [
  // left forewing, its folded face, left hindwing
  { points: '45,47 15,7 2,29 26,49', lit: false },
  { points: '45,47 26,49 37,41', lit: true },
  { points: '44,53 27,54 10,80 34,70', lit: false },
  // the same three, mirrored about the body's axis
  { points: '51,47 81,7 94,29 70,49', lit: false },
  { points: '51,47 70,49 59,41', lit: true },
  { points: '52,53 69,54 86,80 62,70', lit: false },
]

/** One figure, two faces: the moth and the letter it turns from are drawn on this
 *  grid, with this stroke weight and these four tones, so the thinking sign is one
 *  creature seen at two moments of one turn and not two drawings that happen to match. */
function Glyph({
  testId,
  className,
  size,
  planes,
  children,
}: {
  testId: string
  className: string
  size: string
  planes: Array<{ points: string; lit: boolean }>
  children?: ReactNode
}) {
  return (
    <svg
      data-testid={testId}
      viewBox="0 0 96 96"
      width={size}
      height={size}
      aria-hidden="true"
      className={`shrink-0 ${className}`}
      strokeWidth={1.5}
      strokeLinejoin="round"
    >
      {planes.map((plane, index) => (
        <polygon
          key={index}
          points={plane.points}
          fill={plane.lit ? 'var(--color-figure-paper-lit)' : 'var(--color-figure-paper)'}
          stroke="var(--color-figure-paper-shade)"
        />
      ))}
      {children}
    </svg>
  )
}

export function PaperMothGlyph({
  size = '18px',
  className = '',
  testId = 'paper-moth-glyph',
}: {
  /** A CSS length; the glyph scales through its own viewBox. */
  size?: string
  className?: string
  testId?: string
}) {
  return (
    <Glyph testId={testId} className={className} size={size} planes={WINGS}>
      <path d="M44.4,40 L51.6,40 L50.2,53 L48,70 L45.4,53 Z" fill="var(--color-firefly)" />
      <circle className="moth-knot is-left" cx="43" cy="52" r="2.6" fill="var(--color-firefly)" />
      <circle className="moth-knot is-right" cx="53" cy="52" r="2.6" fill="var(--color-firefly)" />
    </Glyph>
  )
}

/** The spine, three arms, and the lit underside of each fold — the fold the wings carry.
 *  The knot at the middle arm's tip is the moth's own firefly, spent once. */
const LETTER: Array<{ points: string; lit: boolean }> = [
  { points: '24,12 38,12 38,84 24,84', lit: false }, // spine
  { points: '38,12 72,15 72,29 38,26', lit: false }, // top arm
  { points: '38,12 72,15 38,26', lit: true },
  { points: '38,41 62,44 62,58 38,55', lit: false }, // middle arm
  { points: '38,41 62,44 38,55', lit: true },
  { points: '38,70 72,67 72,81 38,84', lit: false }, // bottom arm
  { points: '38,84 72,81 38,70', lit: true },
]

export function PaperLetterGlyph({
  size = '18px',
  className = '',
  testId = 'paper-letter-glyph',
}: {
  /** A CSS length; the glyph scales through its own viewBox. */
  size?: string
  className?: string
  testId?: string
}) {
  return (
    <Glyph testId={testId} className={className} size={size} planes={LETTER}>
      <circle cx="62" cy="51" r="2.6" fill="var(--color-firefly)" />
    </Glyph>
  )
}
