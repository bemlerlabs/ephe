/**
 * The meta values the status popover carries: backend uptime, free disk and the
 * per-session auto read-aloud toggle. They used to sit in the header toolbar; the
 * popover keeps them one disclosure away from the quiet status line.
 */
import { useEffect, useState } from 'react'
import { Volume2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AUTOSPEAK_CHANGED_EVENT, isAutospeakActive, setAutospeak } from '@/lib/autospeak'
import { formatFree, useSystemMetrics } from './MetricsGauges'

export function ToolbarMeta({ sessionId }: { sessionId?: string }) {
  const { t } = useTranslation()
  const metrics = useSystemMetrics()
  const [autoSpeak, setAutoSpeakState] = useState(() => isAutospeakActive(sessionId))
  useEffect(() => {
    setAutoSpeakState(isAutospeakActive(sessionId))
    const sync = () => setAutoSpeakState(isAutospeakActive(sessionId))
    window.addEventListener(AUTOSPEAK_CHANGED_EVENT, sync)
    return () => window.removeEventListener(AUTOSPEAK_CHANGED_EVENT, sync)
  }, [sessionId])

  const uptimeMin =
    metrics?.uptime_s != null && Number.isFinite(metrics.uptime_s)
      ? Math.max(1, Math.round(metrics.uptime_s / 60))
      : null

  return (
    <div
      className="hidden md:flex items-center gap-2 text-ui-xs text-ink-faint min-w-0"
      data-testid="toolbar-meta"
    >
      {uptimeMin !== null && (
        <span
          className="tabular-nums truncate min-w-0"
          title={t('toolbar.uptime')}
          aria-label={t('toolbar.uptime')}
        >
          {t('toolbar.uptimeShort', { minutes: uptimeMin })}
        </span>
      )}
      {metrics && metrics.disk_free_bytes > 0 && (
        <span
          className="tabular-nums truncate min-w-0"
          title={t('metrics.free')}
          aria-label={t('metrics.free')}
        >
          {formatFree(metrics.disk_free_bytes, t)}
        </span>
      )}
      <button
        onClick={() => setAutospeak(sessionId, !autoSpeak)}
        aria-pressed={autoSpeak}
        aria-label={t('toolbar.autoSpeak')}
        data-testid="toolbar-autospeak"
        className={`inline-flex items-center gap-1.5 min-w-0 min-h-6 rounded-md px-1.5 py-0.5 transition-colors ${
          autoSpeak
            ? 'text-brand bg-brand/20'
            : 'text-ink-faint hover:text-foreground/70 hover:bg-surface-interactive'
        }`}
      >
        <Volume2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate min-w-0">{t('toolbar.autoSpeak')}</span>
      </button>
    </div>
  )
}
