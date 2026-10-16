import { CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { Activity } from '@/types'

/**
 * Inline activity feed (PWA chat-UX plan, task B3).
 * Phase transitions (fast path, quality check, swarm agents …) stay unobtrusive
 * inline. aria-live="polite": the screen reader announces transitions.
 *
 * UI/UX wave (parity harness): the raw tool lines (`name(...)` /
 * `name → …`) are NO LONGER shown as a feed line of their own — the
 * ToolCallDisplay cards (`>` lines) already present the same calls
 * compactly. The duplication would have been the pile-up at the start.
 * Phase/artefact/swarm labels (without the bracket/arrow pattern) stay. The
 * feed is additionally capped at the last N entries (expandable via the title).
 */
const FEED_CAP = 8

/** Tool-like raw lines: `name(args…)` or `name → …` (covered by ToolCallDisplay). */
function isRawToolLine(label: string): boolean {
  return /^[a-z_][a-z0-9_]*\(/.test(label) || /^[a-z_][a-z0-9_]* →/.test(label)
}

export default function ActivityFeed({ activities }: { activities?: Activity[] }) {
  const { t } = useTranslation()
  if (!activities || activities.length === 0) return null

  // Hide the raw tool lines (resolves the duplication with ToolCallDisplay).
  const shown = activities.filter((a) => !isRawToolLine(a.label))
  if (shown.length === 0) return null
  const overflow = Math.max(0, shown.length - FEED_CAP)
  const visible = overflow > 0 ? shown.slice(shown.length - FEED_CAP) : shown

  return (
    <div aria-live="polite" className="mt-2 space-y-1">
      {overflow > 0 && (
        <div className="pl-5 text-ui-xs text-ink-faint" data-testid="activity-overflow">
          {t('chat.activityMore', { n: overflow })}
        </div>
      )}
      {visible.map((a) => (
        <div key={a.id} className="space-y-0.5">
          <div className="flex items-center gap-2 text-ui-xs" data-testid={`activity-${a.id}`}>
            {a.status === 'running' ? (
              <Loader2 className="h-3 w-3 shrink-0 text-brand animate-spin" aria-hidden="true" />
            ) : a.status === 'done' ? (
              <CheckCircle2 className="h-3 w-3 shrink-0 text-status-success" aria-hidden="true" />
            ) : (
              <XCircle className="h-3 w-3 shrink-0 text-status-danger" aria-hidden="true" />
            )}
            <span className={a.status === 'running' ? 'text-ink-faint' : 'text-ink-soft'}>
              {a.label}
            </span>
            {/* The status is carried by the icon colour alone for sighted users;
                the label keeps it available to the screen reader (WCAG 1.3.1). */}
            <span className="sr-only">
              {a.status === 'running'
                ? t('chat.rowWorking')
                : a.status === 'done'
                  ? t('chat.rowCompleted')
                  : t('chat.rowFailed')}
            </span>
          </div>
          {/* K3 Z09: child events indented under the parent line (swarm nest) */}
          {a.detail && (
            <div
              data-testid={`activity-detail-${a.id}`}
              className="pl-5 text-ui-sm leading-relaxed text-ink-faint whitespace-pre-wrap break-words"
            >
              {a.detail}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/** P3 : agent/swarm activities — the lines stay after the turn ends. */
function isAgentActivity(a: Activity): boolean {
  return /agent|swarm/i.test(a.label)
}

/**
 * P3 : persistent agent lines („Explore · Completed").
 *
 * The transient feed above disappears with the end of the stream (deploy polish
 * P2-6) — but subagent/swarm lines should stay visible AFTER the turn, as in the
 * reference product. A pure derivation from `m.activities` (no store change, no
 * new block kind): the rows render compactly as „icon + label · status" with a
 * spinner on running items; a click opens the subagents tab (PREVIEW_OPEN_EVENT
 * pattern, like the subagent tool line).
 */
export function AgentActivityRows({ activities }: { activities?: Activity[] }) {
  const { t } = useTranslation()
  const agentRows = (activities ?? []).filter(isAgentActivity)
  if (agentRows.length === 0) return null

  const suffixFor = (status: Activity['status']) =>
    status === 'running'
      ? t('chat.rowWorking', { defaultValue: 'Working' })
      : status === 'done'
        ? t('chat.rowCompleted', { defaultValue: 'Completed' })
        : t('chat.rowFailed', { defaultValue: 'Failed' })

  return (
    <div
      data-testid="agent-activity-rows"
      className="mt-1 inline-flex flex-col items-start gap-0.5 max-w-full"
    >
      {agentRows.map((a) => (
        <button
          key={a.id}
          type="button"
          data-testid={`agent-activity-${a.id}`}
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'subagents' } }),
            )
          }
          className="flex items-center gap-2 min-w-0 w-full px-1.5 py-1 rounded-md text-left hover:bg-surface-interactive transition-colors"
        >
          {a.status === 'running' ? (
            <Loader2 className="h-3 w-3 shrink-0 text-brand animate-spin" aria-hidden="true" />
          ) : a.status === 'done' ? (
            <CheckCircle2 className="h-3 w-3 shrink-0 text-status-success" aria-hidden="true" />
          ) : (
            <XCircle className="h-3 w-3 shrink-0 text-status-danger" aria-hidden="true" />
          )}
          <span className="text-ui-xs text-ink-soft truncate min-w-0">{a.label}</span>
          <span
            data-testid={`agent-activity-status-${a.id}`}
            className={`text-ui-xs shrink-0 ${
              a.status === 'running'
                ? 'text-ink-soft'
                : a.status === 'failed'
                  ? 'text-status-danger'
                  : 'text-ink-faint'
            }`}
          >
            {'· '}
            {suffixFor(a.status)}
          </span>
        </button>
      ))}
    </div>
  )
}
