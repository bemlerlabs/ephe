import { Sparkles, Loader2, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { fmtDurationUnits } from '@/lib/format'

/** K3 Z08: elapsed-time format — delegates to the central core (P6 A2). */

/** P6 timeline (ref-01): "Working for Xm Ys" live on the stream, "Worked for …"
 *  with the measured wall time on a finished turn; the chevron collapses the
 *  event rows (the answer stays visible — the split cut). */
export function TurnHeadRow({
  streaming,
  startTs,
  durationMs,
  failed,
  hasTimeline,
  collapsed,
  onToggle,
}: {
  streaming: boolean
  startTs: number
  durationMs?: number
  failed?: boolean
  hasTimeline: boolean
  collapsed: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const live = Math.max(0, Date.now() - startTs)
  const label = streaming
    ? t('chat.turnWorking', { time: fmtDurationUnits(live) })
    : failed
      ? t('chat.turnFailed')
      : durationMs != null
        ? t('chat.turnWorked', { time: fmtDurationUnits(durationMs) })
        : null
  if (!label) return null
  return (
    <button
      type="button"
      data-testid="bubble-turn-head"
      aria-expanded={!collapsed}
      onClick={streaming || !hasTimeline ? undefined : onToggle}
      className="flex items-center gap-1.5 px-0.5 pb-1.5 text-ui-xs text-ink-faint hover:text-foreground/80 transition-colors cursor-pointer"
    >
      {streaming ? (
        <Loader2 className="h-3 w-3 animate-spin shrink-0 text-brand/80" />
      ) : (
        <Sparkles className="h-3 w-3 shrink-0 text-ink-faint" />
      )}
      <span>{label}</span>
      {!streaming && hasTimeline && (
        <ChevronDown
          className={`h-3 w-3 shrink-0 transition-transform ${collapsed ? '-rotate-90' : ''}`}
          aria-hidden="true"
        />
      )}
    </button>
  )
}
