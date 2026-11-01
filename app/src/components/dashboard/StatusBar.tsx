import { useEffect, useMemo, useState } from 'react'
import type { ChatMessage } from '@/types'
import { estimateTokens, formatPercent, WARN_THRESHOLD } from '@/lib/contextMeter'
import { useContextOccupancy } from '@/lib/useContextOccupancy'
import { formatNumber, formatRate } from '@/lib/dateLocale'
import { useChatStore } from '@/store/chatStore'
import { Zap, Shrink } from 'lucide-react'
import { sessionCostUsd, cacheSharePercent } from '@/lib/cost'
import { useTranslation } from 'react-i18next'
import AgentStatusButton from './AgentStatusButton'
import { contextRingLabel } from './chat/contextRing'
import { windowHint } from './statusBar/windowHint'
import { ConnectionPill } from './statusBar/ConnectionPill'
import { ContextWindowsPopover } from './statusBar/ContextWindowsPopover'
import { StorageFootprint } from './statusBar/StorageFootprint'
import { CostChips } from './statusBar/CostChips'
import CodebaseStatusBarPill from './CodebaseStatusBarPill'
import CodebaseIndexDialog from './CodebaseIndexDialog'

/**
 * Ephe — context meter + status bar (P2-5)
 *
 * Shows a session's live context occupancy (%-full meter) and the token
 * breakdown by role. From WARN_THRESHOLD on: an optional "Compact now" button
 * (Phase F) — renders only with `onCompact` (ChatLayout).
 *
 * Offline-first: the occupancy is estimated purely from the messages — no
 * backend fetch needed.
 */

interface StatusBarProps {
  messages: ChatMessage[]
  windowTokens?: number
  /** Phase F: compact action (ChatLayout → store.compactSession) */
  onCompact?: () => void
  /** Header offload (reference image 2): connection + AI activity in the status row */
  backendOnline?: boolean | null
  engineOnline?: boolean | null
  typing?: boolean
}

export default function StatusBar({
  messages,
  windowTokens,
  onCompact,
  sessionId,
  backendOnline,
  engineOnline,
  typing,
}: StatusBarProps & { sessionId?: string }) {
  const { t, i18n } = useTranslation()
  // P0-1: the effective window follows the active provider — the backend value
  // (env override > engine probe > tier table) beats the frontend default 8192.
  // One derivation, shared with the composer's ring (F8).
  const {
    budget,
    window: effectiveWindow,
    usage,
    percent: effectivePercent,
    tokens: effectiveTokens,
    remaining: effectiveRemaining,
    tokenizer,
  } = useContextOccupancy(messages, windowTokens, sessionId)

  const turnUsage = useChatStore((s) => s.lastTurnUsage)

  // Wave 3 (cost monitor & cache chip): both chips come ONLY from measured values —
  // pricing from engine.json (via /api/model/providers), totals from usage frames.
  // If the price or the measurement is missing the chip stays off (never guess a number).
  const usageTotals = useChatStore((s) => s.currentSession?.usageTotals)
  const enginePricing = useChatStore((s) => s.enginePricing)
  const sessionCost = useMemo(
    () => sessionCostUsd(usageTotals, enginePricing),
    [usageTotals, enginePricing],
  )
  const cachePercent = useMemo(
    () => cacheSharePercent(usageTotals, turnUsage),
    [usageTotals, turnUsage],
  )

  const [expanded, setExpanded] = useState(false)
  const [codebaseOpen, setCodebaseOpen] = useState(false)

  // R25: compaction status as an honest hint (the backend counts, not a feeling)
  const compactionActive = budget?.compaction_active ?? false

  // The meter's disclosure, said once: what the bar is measured against, or what it is
  // waiting for. The popover repeats the same sentence.
  const meterHint = compactionActive
    ? t('statusBar.compactionActive')
    : windowHint(budget, effectiveWindow ?? 0, t, i18n.language)

  // tokens/sec of the active streaming answer: output tokens / elapsed time since
  // turn start (message.timestamp). Ticked live, only while streaming.
  const active = messages?.find((m) => m.role === 'assistant' && m.streaming)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(id)
  }, [active])
  const tokPerSec = useMemo(() => {
    if (!active) return null
    const secs = (now - active.timestamp) / 1000
    if (secs < 0.5) return null
    // DD-08: the thinking phase streams before the first content token — without
    // counting that channel the rate sat at 0.0 throughout the reasoning.
    const streamed = (active.content ?? '') + (active.thinking?.text ?? '')
    return estimateTokens(streamed) / secs
  }, [active, now])

  const warn = effectivePercent / 100 >= WARN_THRESHOLD
  const danger = effectivePercent >= 95
  const meterColor = danger ? 'bg-status-danger' : warn ? 'bg-status-warning' : 'bg-status-success'

  return (
    <div
      data-testid="status-bar"
      // The last surface of the chat column: installed on a phone the home
      // indicator is drawn over it, so this row carries the bottom inset. The
      // composer sits above it and needs none.
      // QD-015 V1: one line, always. The row used to wrap below lg, and a
      // wrapped second line painted into the popover's space while the right
      // panel squeezed the column. The width hierarchy now hides the secondary
      // figures in steps (md, lg, xl) and lets the meter absorb the remainder.
      className="border-b border-hairline px-3 pt-1.5 pb-[calc(0.375rem+env(safe-area-inset-bottom))] max-lg:pb-1.5 flex items-center gap-2 flex-shrink-0 select-none overflow-hidden whitespace-nowrap"
    >
      {/* Reference image 2: two pills on the left — 'Expand status' + current activity */}
      <div className="hidden sm:flex items-center shrink-0">
        <AgentStatusButton messages={messages ?? []} sessionId={sessionId} />
      </div>
      {typing === true && (
        <span
          className="hidden lg:inline-flex items-center gap-1.5 text-ui-xs text-brand/80"
          data-testid="ki-activity"
          role="status"
          aria-label={t('metrics.activity')}
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-50" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-brand" />
          </span>
          {t('metrics.activity')}
        </span>
      )}
      {/* Live tok/s of the active answer — always visible (minimal footer,
          reference: a slim terminal-harness line), not only in the popover. */}
      {typing === true && (tokPerSec ?? 0) > 0 && (
        <span
          data-testid="statusbar-tok-per-sec"
          className="hidden sm:inline-flex items-center gap-1 text-ui-xs font-mono tabular-nums text-brand/90 shrink-0"
          title={t('statusBar.tokPerSecHint')}
        >
          <Zap className="h-3 w-3 text-brand/70" />
          {formatRate(tokPerSec ?? 0, i18n.language)} tok/s
        </span>
      )}
      {/* E-phase UX: the CPU/RAM/Disk gauges + uptime/auto-read-aloud now live in
          the agent-status popover („Status aufklappen") — the visible row stays
          minimal: one pill per fact, nothing more. */}
      <ConnectionPill backendOnline={backendOnline} engineOnline={engineOnline} />
      <div className="hidden md:inline-flex min-w-0 max-w-[12rem]">
        <CodebaseStatusBarPill onOpen={() => setCodebaseOpen(true)} />
      </div>
      {/* Live %-full Meter. R36 (Judge R2): percent lives OUTSIDE the meter
          div — as a squeezed flex-1 child it painted over the neighboring tok
          pill (overflow visible). Both are root children with gap + shrink-0
          now; the bar itself yields when the row runs out of space. */}
      <div className="flex items-center min-w-0 flex-1">
        {/* F2's sibling: the composer ring got `role="img"` and a name, the row meter
            did not — its occupancy lived in a `title` alone. Same sentence as the ring,
            from the same key, so the two readouts of one number speak alike. */}
        <div
          data-testid="statusbar-meter"
          role="img"
          aria-label={contextRingLabel(t, effectivePercent, i18n.language)}
          className="w-full h-1.5 rounded-full bg-surface overflow-hidden max-w-[120px]"
          title={meterHint}
        >
          <div
            className={`h-full rounded-full transition-all ${meterColor}`}
            style={{ width: `${effectivePercent}%` }}
          />
        </div>
      </div>
      <span
        data-testid="statusbar-percent"
        className={`text-ui-xs font-mono tabular-nums shrink-0 ${danger ? 'text-status-danger' : warn ? 'text-status-warning' : 'text-ink-soft'}`}
      >
        {formatPercent(effectivePercent, i18n.language)}
        {compactionActive && (
          <span
            data-testid="statusbar-compaction-marker"
            className="ml-1 text-ink-faint"
            title={t('statusBar.compactionActive')}
          >
            ·S
          </span>
        )}
      </span>
      {tokenizer === 'tiktoken-bpe' && (
        <span
          data-testid="statusbar-tokenizer-chip"
          className="hidden lg:inline text-ui-xs font-mono text-ink-faint shrink-0"
          title={t('status.bpeExact')}
        >
          ·bpe
        </span>
      )}

      {/* DD-22: the auto-read-aloud toggle was here AND in the toolbar row — the
          same control twice (same setAutospeak(sessionId), same localStorage) —
          the redundancy stood out as visual load in the deep dive.
          The toolbar row (ToolbarRow) is the only place for it. */}

      {/* Token breakdown (toggle on click) — W19 F5: the secondary metrics
          tok/s and TTFT now live in the context popover instead of their own
          pills in the row (compact status bar). */}
      <button
        onClick={() => setExpanded((v) => !v)}
        data-testid="statusbar-breakdown-toggle"
        aria-expanded={expanded}
        aria-haspopup="dialog"
        className="hidden lg:flex text-ui-xs font-mono tabular-nums text-ink-faint hover:text-foreground/60 transition-colors items-center gap-1 py-1.5 -my-1.5 px-1 -mx-1 whitespace-nowrap shrink-0"
        title={t('statusBar.breakdownHint')}
      >
        <Zap className="h-3 w-3 text-brand/70" />
        <span>
          {formatNumber(effectiveTokens, i18n.language)} tok
          {expanded && (
            <span className="text-ink-faint">
              {' '}
              (U {formatNumber(usage.tokens.user, i18n.language)} · A{' '}
              {formatNumber(usage.tokens.assistant, i18n.language)} · S{' '}
              {formatNumber(usage.tokens.system, i18n.language)})
            </span>
          )}
        </span>
      </button>

      <CostChips
        usageTotals={usageTotals}
        enginePricing={enginePricing}
        sessionCost={sessionCost}
        cachePercent={cachePercent}
      />

      {/* R44 (P3): IndexedDB footprint — N sessions · ~MB. The pill is purely
          readable (no toggle); it counts the browser sessions and their JSON
          length, so a nearing quota warns before the silent loss.
          R36: min-w-0 + truncate — as the last pill in the row it yields instead
          of painting over "N free" (judge R2). */}
      <div className="hidden xl:inline-flex min-w-0">
        <StorageFootprint />
      </div>

      {/* DD-10: on mobile there was no token figure at all — the breakdown button
          is md:flex. An equivalent md:hidden counterpart (same toggle) so desktop
          and mobile show the same information. */}
      <button
        onClick={() => setExpanded((v) => !v)}
        data-testid="statusbar-tok-chip"
        aria-expanded={expanded}
        aria-haspopup="dialog"
        className="lg:hidden text-ui-xs font-mono tabular-nums text-ink-soft py-1.5 -my-1.5 px-1 shrink-0"
      >
        {formatNumber(effectiveTokens, i18n.language)} tok
      </button>

      {/* F1: a free figure without its total is a number with no unit. The window
          goes where the reader already looks for the remainder.
          QD-015 V1: the remainder is the first figure to give way — below md it
          steps out entirely, and above it `min-w-0 truncate` lets it shrink
          against the cost chips instead of pushing them into a second row. */}
      <span className="hidden md:inline-block min-w-0 truncate text-ui-xs text-ink-faint font-mono tabular-nums">
        {effectiveWindow
          ? t('statusBar.contextFreeOf', {
              free: formatNumber(effectiveRemaining, i18n.language),
              window: formatNumber(effectiveWindow, i18n.language),
            })
          : `${formatNumber(effectiveRemaining, i18n.language)} ${t('statusBar.contextFree')}`}
      </span>

      {warn && onCompact && (
        <button
          onClick={onCompact}
          className="text-ui-xs font-medium text-status-warning bg-status-warning/10 hover:bg-status-warning/20 rounded-md px-1.5 py-0.5 flex items-center gap-1 transition-colors"
          title={t('chat.compactBanner')}
        >
          <Shrink className="h-3 w-3" />
          {t('chat.compactNow')}
        </button>
      )}
      {expanded && (
        <ContextWindowsPopover
          budget={budget}
          tokens={effectiveTokens}
          window={effectiveWindow ?? 0}
          percent={effectivePercent}
          compactionActive={compactionActive}
          tokPerSec={tokPerSec}
          ttftMs={active?.ttftMs ?? null}
        />
      )}
      <CodebaseIndexDialog open={codebaseOpen} onClose={() => setCodebaseOpen(false)} />
    </div>
  )
}
