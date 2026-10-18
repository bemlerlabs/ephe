import { Send, Square } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { WARN_THRESHOLD } from '@/lib/contextMeter'
import { contextRingLabel } from './contextRing'

/**
 * E-UX: the composer's right-hand complex — context ring + send/stop button +
 * queue badge. Extracted from ChatInput.tsx.
 */
export default function ComposerSendButton({
  streaming,
  sendDisabled,
  onSend,
  onStop,
  contextPercent,
  queueCount,
}: {
  streaming: boolean
  sendDisabled: boolean
  onSend: () => void
  onStop?: () => void
  contextPercent: number | null
  queueCount: number
}) {
  const { t, i18n } = useTranslation()
  return (
    <div
      className="relative shrink-0"
      role="img"
      aria-label={contextRingLabel(t, contextPercent, i18n.language)}
      title={contextRingLabel(t, contextPercent, i18n.language)}
    >
      {/* E-UX: context ring (the reference clients use a circle at the
          composer) — progress = context utilisation, colour green →
          yellow (warn threshold) → red; subtle behind the send button.
          Smarter than a plain circle: as soon as any context exists, a
          MINIMUM ARC of 2 % shows the ring is alive — otherwise it
          disappears for huge windows (0.07 %). */}
      {contextPercent != null && contextPercent > 0 && (
        <svg
          data-testid="composer-context-ring"
          aria-hidden="true"
          className="absolute -inset-1 pointer-events-none"
          viewBox="0 0 44 44"
        >
          <circle
            cx="22"
            cy="22"
            r="20"
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="2.5"
          />
          <circle
            cx="22"
            cy="22"
            r="20"
            fill="none"
            strokeWidth="2.5"
            strokeLinecap="round"
            className={
              contextPercent >= 95
                ? 'stroke-status-danger'
                : contextPercent >= WARN_THRESHOLD * 100
                  ? 'stroke-status-warning'
                  : 'stroke-brand'
            }
            strokeDasharray={`${(Math.max(Math.min(contextPercent, 100), 2) / 100) * 2 * Math.PI * 20} ${2 * Math.PI * 20}`}
            transform="rotate(-90 22 22)"
          />
        </svg>
      )}
      <button
        onClick={streaming ? onStop : onSend}
        disabled={sendDisabled}
        aria-label={streaming ? t('chat.stop') : t('chat.send')}
        data-testid={streaming ? 'stop-btn' : 'send-btn'}
        className={
          streaming
            ? 'bg-status-danger/80 hover:bg-status-danger text-foreground rounded-full p-2 max-lg:p-3 transition-all duration-base shrink-0 min-h-9 min-w-9 max-lg:min-h-11 max-lg:min-w-11'
            : 'bg-brand hover:bg-brand-glow disabled:opacity-30 disabled:cursor-not-allowed text-black rounded-full p-2 max-lg:p-3 transition-all duration-base forest-glow shrink-0 min-h-9 min-w-9 max-lg:min-h-11 max-lg:min-w-11'
        }
      >
        {streaming ? <Square className="h-4 w-4" /> : <Send className="h-4 w-4" />}
      </button>
      {/* Reference parity «Keep typing to queue»: the queue counter
          sits right on the stop button, not only in the row below. */}
      {streaming && queueCount > 0 && (
        <span
          data-testid="composer-queue-badge"
          aria-label={t('chat.queueHint', { count: queueCount })}
          className="absolute -top-1.5 -right-1.5 z-10 rounded-full bg-status-info px-1.5 min-w-4 text-center text-ui-2xs font-mono leading-4 text-black shadow-elevation-1"
        >
          {queueCount}
        </span>
      )}
    </div>
  )
}
