import { ArrowDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/**
 * The running plan's position, where the reader looks while scrolling back:
 * a quiet pill over the transcript that also jumps to the live edge.
 */
export function StepPill({
  step,
  total,
  onJump,
}: {
  step: number
  total: number
  onJump: () => void
}) {
  const { t } = useTranslation()
  if (total < 2) return null
  const at = Math.min(Math.max(1, step), total)
  return (
    <button
      type="button"
      onClick={onJump}
      data-testid="step-pill"
      className="absolute bottom-4 left-1/2 z-sticky flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-hairline bg-elevated px-3 py-1.5 text-ui-xs text-ink-soft shadow-lg transition-colors hover:text-foreground"
    >
      <span className="tabular-nums">{t('chat.stepPill', { n: at, total })}</span>
      <ArrowDown className="h-3 w-3" strokeWidth={1.5} aria-hidden="true" />
    </button>
  )
}
