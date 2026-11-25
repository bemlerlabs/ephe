import { useEffect, useState } from 'react'
import { BrainCircuit, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDurationShort, formatThinkingLabel } from '@/lib/thinking'
import { useDeepBool } from '@/lib/deepSettings'
import { ThinkingMark } from '@/components/brand/ThinkingMark'
import type { ThinkingPhase } from '@/types'

/**
 * AI-client-style thinking block (PWA-Chat-UX-Plan, task B1 + thinking stream)
 *
 * - thinking === null        → renders nothing (legacy / no thinking)
 * - thinking.end === null     → the thinking sign plus live `chat.thinkingNow` and a
 *                               per-second tick (the word is the locale's, the turn is
 *                               the sign's — see components/brand/ThinkingMark.tsx)
 *                               + streamed reasoning text (tail window, aria-busy)
 * - thinking.end !== null     → collapsible `chat.thoughtForSeconds` =
 *                               "Thought for Ns" (expand = reasoning)
 *
 * Only an open phase is a thinking state. A finished phase, a tool about to run and
 * an answer that streams are other states and carry no sign.
 */
export default function ThinkingBlock({ thinking }: { thinking: ThinkingPhase | null }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  // P3: ticking seconds display for as long as the phase is open (end === null)
  // — a 1s interval like useStatusPanelData.nowTick, cleaned up by the effect;
  // finished phases render statically from start/end.
  const running = thinking !== null && thinking.end === null
  // I6-3: `chat.show_thinking_loader` switches off the whole live line — sign, word
  // and the 1s tick with it. The reasoning text below it stays and is
  // gated by `chat.show_reasoning` (otherwise one field would have two effects).
  const showLoader = useDeepBool('chat.show_thinking_loader', true)
  const [nowTick, setNowTick] = useState(() => Date.now())
  useEffect(() => {
    if (!running || !showLoader) return
    setNowTick(Date.now())
    const handle = setInterval(() => setNowTick(Date.now()), 1000)
    return () => clearInterval(handle)
  }, [running, showLoader])

  if (!thinking) return null

  const text = thinking.text ?? ''

  if (running) {
    return (
      <div className="mt-1" aria-busy="true" data-testid="thinking-block">
        {showLoader && (
          <div className="flex items-center gap-2 text-ui-xs text-ink-soft">
            {/* One live region for the state: the sign is decoration and stays out of
                the name, the word is the announcement. The tick sits outside it on
                purpose — a polite region that carried the second counter would read
                itself again every second. */}
            <span
              data-testid="thinking-status"
              className="inline-flex items-center gap-1.5"
              role="status"
              aria-live="polite"
            >
              <ThinkingMark />
              <span>{t('chat.thinkingNow')}</span>
            </span>
            <span data-testid="thinking-timer" className="font-mono text-ink-faint">
              {'· '}
              {formatDurationShort(nowTick - thinking.start)}
            </span>
          </div>
        )}
        {text && (
          <div className="ml-3.5 mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap break-words text-ui-xs leading-relaxed text-ink-faint font-mono">
            {text.slice(-1600)}
          </div>
        )}
      </div>
    )
  }

  if (!thinking.end) return null
  const ms = thinking.end - thinking.start
  return (
    <div className="mt-1" data-testid="thinking-block">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex items-center gap-1.5 text-ui-xs text-ink-soft hover:text-foreground/60 transition-colors"
      >
        {/* P6 (ref-01): icon + label + duration as one quiet line. */}
        <BrainCircuit className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
        <ChevronRight className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        {formatThinkingLabel(ms, t)}
      </button>
      {expanded && (
        <div className="ml-5 mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words text-ui-xs leading-relaxed text-ink-faint">
          {text || <span className="text-ink-faint italic">{t('chat.thinkingEmpty')}</span>}
        </div>
      )}
    </div>
  )
}
