import { useEffect, useState } from 'react'
import { BrainCircuit, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDurationShort, formatThinkingLabel } from '@/lib/thinking'
import { useDeepBool } from '@/lib/deepSettings'
import type { ThinkingPhase } from '@/types'

/**
 * AI-client-style thinking block (PWA-Chat-UX-Plan, task B1 + thinking stream)
 *
 * - thinking === null        → renders nothing (legacy / no thinking)
 * - thinking.end === null     → live `chat.thinkingNow` + a per-second tick
 *                               (Ephe norm for the timer: "Thought · Ns"; the
 *                               German locale reads „Denkt nach…" — language-gate: ignore: quoted product label)
 *                               + streamed reasoning text (tail window, aria-busy)
 * - thinking.end !== null     → collapsible `chat.thoughtForSeconds` =
 *                               "Thought for Ns" (expand = reasoning)
 */
export default function ThinkingBlock({ thinking }: { thinking: ThinkingPhase | null }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  // P3: ticking seconds display for as long as the phase is open (end === null)
  // — a 1s interval like useStatusPanelData.nowTick, cleaned up by the effect;
  // finished phases render statically from start/end.
  const running = thinking !== null && thinking.end === null
  // I6-3: `chat.show_thinking_loader` switches off the pulsing "Thinking… · Ns"
  // line together with its 1s tick. The reasoning text below it stays and is
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
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
            <span>{t('chat.thinkingNow')}</span>
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
        {/* P6 (ref-01): icon + label + duration as one quiet line — "🧠 Thought · 5s" */}
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
