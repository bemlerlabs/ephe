'use client'

/**
 * The thinking sign: the letter that turns into the moth for as long as the engine
 * reasons, and back again when it starts answering.
 *
 * One square, two faces, one axis. Both faces are the brand's own glyphs — the moth is
 * `PaperMothGlyph`, the letter `PaperLetterGlyph`, drawn on the same grid in the same
 * file — standing in the same grid cell while the stage turns on its own vertical
 * axis. The swap therefore happens at the frame that is edge-on: nothing in the line
 * shifts, nothing is repainted, and only `transform` moves.
 *
 * It carries no word. The word beside it belongs to the locale bundles, so a run says
 * it in the reader's language; this file draws and names nothing.
 */
import { PaperLetterGlyph, PaperMothGlyph } from './PaperMothGlyph'
import './ThinkingMark.css'

export function ThinkingMark({
  size = '1.125rem',
  className = '',
  testId = 'thinking-mark',
}: {
  /** A CSS length. Both faces scale through their shared viewBox. */
  size?: string
  className?: string
  testId?: string
}) {
  return (
    <span
      data-testid={testId}
      aria-hidden="true"
      className={`ephe-think ${className}`}
      style={{ ['--ephe-think-size' as string]: size }}
    >
      <span className="ephe-think-stage">
        <span className="ephe-think-frame" data-face="letter">
          <PaperLetterGlyph size="100%" testId={`${testId}-letter`} />
        </span>
        <span className="ephe-think-frame" data-face="moth">
          <PaperMothGlyph size="100%" testId={`${testId}-moth`} />
        </span>
      </span>
    </span>
  )
}
