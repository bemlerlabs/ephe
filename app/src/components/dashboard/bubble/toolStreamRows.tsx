import { useState, useEffect, useMemo, useRef } from 'react'
import { ChevronRight, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useDeepBool, useDeepSelect } from '@/lib/deepSettings'
import { audienceOf, proofText } from '@/lib/proofAudience'
import { fmtMs } from '@/lib/format'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import ToolCallDisplay from '../ToolCallDisplay'
import { ICONS } from '../ToolCallDisplay'
import { aggregateToolCalls } from '@/lib/toolStreamModel'
import type { ToolCallShape } from '@/lib/toolStreamModel'
import { classifyToolCall } from '@/lib/toolCardModel'

/**
 * I1 (2026-09-07): reference-B style aggregated activity rows. Consecutive
 * calls of the same family = one row (icon + label + counter/
 * summary), the chevron expands the existing family cards
 * (ToolCallDisplay) as details — plain in the stream instead of chips-in-one-block.
 */
export function ToolStreamRows({
  tool_calls,
  streaming,
}: {
  tool_calls: ToolCallShape[]
  streaming?: boolean
}) {
  const { t } = useTranslation()
  const showCount = useDeepBool('chat.show_tool_count', true)
  // P1: the same switch that opens the details also picks the wording.
  const detailsMode = useDeepSelect('chat.details_mode', 'expanded')
  const expandFirst = useDeepBool('chat.expand_tool_calls', false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const touched = useRef(false)
  const groups = useMemo(() => aggregateToolCalls(tool_calls), [tool_calls])

  // I6-3: `chat.expand_tool_calls` — the top group starts expanded.
  // It holds until the first own click (touched); otherwise the setting would
  // reopen every manual click the user makes.
  useEffect(() => {
    const first = groups[0]
    if (touched.current || !expandFirst || !first) return
    setOpenGroup(`${first.family}-0`)
  }, [expandFirst, groups])

  if (groups.length === 0) return null

  // R61 rule 2: the run's record is a control pane, and a control veil may rest on
  // the reading pane the assistant bubble carries.
  return (
    <div
      className="glass-control mt-1 inline-flex flex-col items-start gap-0.5 max-w-full"
      data-testid="tool-stream-rows"
    >
      {groups.map((g, i) => {
        const key = `${g.family}-${i}`
        const open = openGroup === key
        const RowIcon =
          ICONS[classifyToolCall(g.calls[0] as Parameters<typeof classifyToolCall>[0]).icon] ??
          ICONS.wrench
        // R42 live cadence: done/total pair while running + stdout tail in the row
        const doneCount = g.calls.filter(
          (c) => (c as { status?: string }).status !== 'pending',
        ).length
        // P6 deep-test finding: after the stream ends no call stays "pending"
        // alive — a bubble that is not streaming may never show the group as
        // "Working" (honest status, otherwise the spinner sticks forever).
        const live = streaming !== false
        const running = live && doneCount < g.count
        // P3 : status suffix at the end of the row — Working/Completed/
        // Failed; running beats failed (the group is still working).
        const rowStatus: 'running' | 'done' | 'failed' = running
          ? 'running'
          : g.hasFailure
            ? 'failed'
            : 'done'
        const groupMs = g.calls.reduce(
          (sum, c) => sum + ((c as { duration_ms?: number }).duration_ms ?? 0),
          0,
        )
        const proof =
          rowStatus === 'running'
            ? null
            : proofText(audienceOf(detailsMode), { ok: !g.hasFailure, ms: groupMs || null })
        const tailSource = [...g.calls]
          .reverse()
          .map((c) => (c as { stdout?: string }).stdout)
          .find((s) => !!s)
        const tailLine = tailSource
          ? tailSource
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
              .slice(-2)
              .join(' ')
          : ''
        // Hovering the row lifts its fill onto the 8% lit step, where both veils leave
        // the muted 11px ink at 3.85:1; the row's ink moves onto --color-ink-soft there.
        return (
          <div key={key} data-testid={`tool-stream-row-${g.family}`}>
            <button
              type="button"
              data-testid={running ? 'tool-stream-row-active' : undefined}
              onClick={() => {
                touched.current = true
                setOpenGroup((v) => (v === key ? null : key))
                // the subagent row additionally opens the detail tab (run details,
                // like the reference pattern: click the row → agent in the tab).
                if (g.family === 'subagent') {
                  window.dispatchEvent(
                    new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'subagents' } }),
                  )
                }
              }}
              aria-expanded={open}
              className="group flex items-center gap-2 min-w-0 w-full px-1.5 py-1 rounded-md text-left hover:bg-surface-interactive transition-colors"
            >
              <ChevronRight
                className={`h-3 w-3 text-ink-faint shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
              />
              {/* P3 : running group → spinner BEFORE the label
                  (instead of the family icon), as in the reference anatomy. */}
              {running ? (
                <Loader2
                  data-testid="tool-row-spinner"
                  className="h-3 w-3 shrink-0 animate-spin text-brand"
                  aria-hidden="true"
                />
              ) : (
                <RowIcon className="h-3 w-3 text-ink-faint shrink-0" aria-hidden="true" />
              )}
              <span
                className={`text-ui-xs shrink-0 ${g.hasFailure ? 'text-status-danger/90' : 'text-ink-soft'}`}
              >
                {t(g.summaryKey)}
                {showCount && g.count > 1 && (
                  <span className="text-ink-faint group-hover:text-ink-soft group-focus-visible:text-ink-soft">
                    {' · '}
                    {running
                      ? `${doneCount}/${g.count}`
                      : t('streamGroup.count', { count: g.count })}
                  </span>
                )}
              </span>
              {proof && (
                <span
                  data-testid="tool-row-proof"
                  className={`tabular-nums text-ui-2xs shrink-0 truncate ${
                    g.hasFailure ? 'text-status-danger/90' : 'text-ink-faint'
                  }`}
                >
                  {t(proof.key, proof.values)}
                </span>
              )}
              {g.target &&
                g.count === 1 &&
                (g.family === 'edit' ||
                  g.family === 'write' ||
                  g.family === 'read' ||
                  g.family === 'subagent') && (
                  <span
                    className={`text-ui-xs text-ink-faint group-hover:text-ink-soft group-focus-visible:text-ink-soft truncate min-w-0 font-mono ${g.family === 'subagent' ? 'font-medium text-ink-soft' : ''}`}
                  >
                    {g.target}
                  </span>
                )}
              {(g.family === 'edit' || g.family === 'write') &&
                (g.additions > 0 || g.deletions > 0) && (
                  <span className="text-ui-xs font-mono shrink-0">
                    {g.additions > 0 && (
                      <span className="text-status-success/90">+{g.additions}</span>
                    )}{' '}
                    {g.deletions > 0 && (
                      <span className="text-status-danger/90">−{g.deletions}</span>
                    )}
                  </span>
                )}
              {/* K3 Z08: elapsed-time chip (from the tool_done frame, ms) */}
              {g.calls
                .map((c) => (c as { duration_ms?: number }).duration_ms)
                .find((d) => d !== undefined) !== undefined && (
                <span
                  data-testid="tool-duration-chip"
                  className="text-ui-xs font-mono text-ink-soft shrink-0"
                >
                  {fmtMs(
                    g.calls
                      .map((c) => (c as { duration_ms?: number }).duration_ms)
                      .find((d) => d !== undefined) as number,
                  )}
                </span>
              )}
              {/* R42: the last stdout lines already live in the collapsed row —
                  the user sees the tool working without expanding it. */}
              {running && tailLine !== '' && (
                <span
                  data-testid="tool-row-tail"
                  className="text-ui-xs font-mono text-ink-soft min-w-0 line-clamp-1"
                >
                  {tailLine}
                </span>
              )}
              {/* P3 : status suffix on the right of the row end —
                  "1/3 · Working" / "· Completed" / "· Failed". */}
              <span
                data-testid="tool-row-status"
                className={`text-ui-xs shrink-0 ${
                  rowStatus === 'running'
                    ? 'text-status-info'
                    : rowStatus === 'failed'
                      ? 'text-status-danger'
                      : 'text-ink-faint group-hover:text-ink-soft group-focus-visible:text-ink-soft'
                }`}
              >
                {'· '}
                {rowStatus === 'running'
                  ? t('chat.rowWorking', { defaultValue: 'Working' })
                  : rowStatus === 'failed'
                    ? t('chat.rowFailed', { defaultValue: 'Failed' })
                    : t('chat.rowCompleted', { defaultValue: 'Completed' })}
              </span>
            </button>
            {open && (
              <div className="pl-4 pb-1">
                <ToolCallDisplay tool_calls={g.calls as never} />
                {/* K3 Z07: stdout tail — growing pre block of the live chunks */}
                {g.calls.map((c, ci) => {
                  const tail = (c as { stdout?: string }).stdout
                  if (!tail) return null
                  const lines = tail.split('\n').slice(-12)
                  return (
                    <pre
                      key={`${g.family}-stdout-${ci}`}
                      data-testid="tool-stdout-tail"
                      className="mt-1 rounded bg-canvas border border-hairline px-2 py-1.5 font-mono text-ui-sm leading-relaxed text-ink-faint whitespace-pre-wrap break-all overflow-x-auto"
                    >
                      {lines.join('\n')}
                    </pre>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
