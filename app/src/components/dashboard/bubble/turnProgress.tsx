import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import type { TurnProgress } from '@/types'

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes > 0 ? `${minutes}m ${rest}s` : `${rest}s`
}

/**
 * S17: the running turn says what it is doing, not just that it runs.
 *
 * "Working for 5m19s" with no other word was the reported defect: the search
 * round was alive, the surface was silent. The event carries the tool, its
 * round (2/4) and the query; the local tick keeps the time honest between the
 * 5 s heartbeats.
 */
export default function TurnProgressLine({ progress }: { progress: TurnProgress }) {
  const { t } = useTranslation()
  const [now, setNow] = useState(() => Date.now())
  const since = useRef(Date.now())
  useEffect(() => {
    since.current = Date.now()
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [progress.elapsedMs])
  const elapsed = Math.max(
    1,
    Math.round((progress.elapsedMs + (now - since.current)) / 1000),
  )
  const time = clock(elapsed)
  const search = progress.tool === 'web_search'
  const label = search
    ? t('chat.searchProgress', { time, round: progress.round, cap: progress.roundCap })
    : t('agentStatus.workingFor', { time })
  return (
    <p
      data-testid="turn-progress"
      className="mt-1.5 flex items-center gap-1.5 text-ui-xs text-ink-soft"
    >
      <Loader2 className="h-3 w-3 animate-spin shrink-0" aria-hidden="true" />
      <span className="truncate" data-testid="turn-progress-label">
        {label}
        {search && progress.query ? ` · ${progress.query}` : ''}
      </span>
      {search && progress.phase !== 'tool_done' && (
        <span className="shrink-0 text-ink-faint">{t('chat.searchWaiting')}</span>
      )}
    </p>
  )
}
