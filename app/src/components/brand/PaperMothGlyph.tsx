'use client'

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
      {WINGS.map((wing, index) => (
        <polygon
          key={index}
          points={wing.points}
          fill={wing.lit ? 'var(--color-figure-paper-lit)' : 'var(--color-figure-paper)'}
          stroke="var(--color-figure-paper-shade)"
        />
      ))}
      <path
        d="M44.4,40 L51.6,40 L50.2,53 L48,70 L45.4,53 Z"
        fill="var(--color-firefly)"
      />
      <circle className="moth-knot is-left" cx="43" cy="52" r="2.6" fill="var(--color-firefly)" />
      <circle className="moth-knot is-right" cx="53" cy="52" r="2.6" fill="var(--color-firefly)" />
    </svg>
  )
}
