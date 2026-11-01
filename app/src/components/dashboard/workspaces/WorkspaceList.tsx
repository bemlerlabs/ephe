/**
 * Ephe — the workspace column of `/workspaces` (W1).
 *
 * One row per checkout an agent run owns: who works there, how long it has been alive,
 * and where it sits on disk. This is the answer to "which agents are running right now"
 * — a row is a live tree, not a task.
 *
 * The count on a row is the number of change sets that row's workspace actually handed
 * back. A workspace whose change sets have not been read yet shows no number at all:
 * `0` would be a claim, and an unread list is not an empty one.
 */
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui'
import { formatDuration } from '@/lib/duration'
import type { Workspace } from '@/lib/api'
import {
  ageOf,
  ageOfSeconds,
  ageText,
  runStateLabel,
  runStateTone,
  vocabLabel,
  workspaceStateTone,
} from './labels'

/** The age of a checkout as a sentence fragment: "just now", "12m", "3h", "2d".
 *
 * A row with a last touch tells when something happened there; one without tells how long
 * the tree has stood. The two used to read the same, so a checkout idle since yesterday
 * looked like a run that started yesterday. The source travels in the label a reader can
 * ask for, so a number never claims to be something it is not. */
export function AgeText({ iso, seconds }: { iso: string; seconds?: number | null }) {
  const { t } = useTranslation()
  const fromEvent = ageOfSeconds(seconds)
  const shown = fromEvent ?? ageOf(iso)
  if (!shown) return null
  const when = ageText(shown, t)
  return (
    <span
      data-testid="workspace-age"
      data-source={fromEvent ? 'activity' : 'created'}
      title={t(fromEvent ? 'workspaces.age.activity' : 'workspaces.age.created', { when })}
    >
      {when}
    </span>
  )
}

export default function WorkspaceList({
  workspaces,
  selectedId,
  onSelect,
  counts,
}: {
  workspaces: Workspace[]
  selectedId: string | null
  onSelect: (id: string) => void
  /** Change sets per workspace id; a missing entry means the list has not been read yet. */
  counts: Record<string, number | undefined>
}) {
  const { t } = useTranslation()

  return (
    <ul
      className="flex flex-col gap-1"
      aria-label={t('workspaces.title')}
      data-testid="workspaces-list"
      role="list"
    >
      {workspaces.map((ws) => {
        const selected = ws.id === selectedId
        const count = counts[ws.id]
        return (
          <li key={ws.id}>
            <button
              type="button"
              onClick={() => onSelect(ws.id)}
              aria-current={selected ? 'true' : undefined}
              data-testid={`workspace-row-${ws.id}`}
              className={`w-full rounded-md px-2.5 py-2 text-left text-ui-xs transition-colors min-h-9 max-lg:min-h-11 focus-ring ${
                selected
                  ? 'bg-brand/10 text-brand-deep'
                  : 'text-ink-faint hover:bg-surface hover:text-foreground/80'
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-medium">{ws.owner || ws.id}</span>
                {/* Double-coded: the tone carries the state, the word says it. Colour
                    alone would be the only reading for a colour-blind reviewer. */}
                <Badge variant={workspaceStateTone(ws.state)} className="shrink-0 px-2 py-0.5">
                  {vocabLabel('state', ws.state, t)}
                </Badge>
              </span>
              <span className="mt-0.5 flex items-center gap-1.5 text-ui-2xs text-ink-faint">
                {ws.branch && <span className="truncate font-mono">{ws.branch}</span>}
                {ws.branch && ws.created_at && <span aria-hidden="true">·</span>}
                <span className="shrink-0 tabular-nums">
                  <AgeText iso={ws.created_at} seconds={ws.last_event?.age_seconds} />
                </span>
                {count !== undefined && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="shrink-0 tabular-nums text-ink-soft">
                      {t('workspaces.changeSetCount', { count })}
                    </span>
                  </>
                )}
              </span>
              {/* The run's own state, beside the register's word for the tree: what the run
                  is *doing* is a different fact from what its checkout looks like, and a run
                  that waits on a person must not read as one that is thinking. Rendered only
                  when the server sends the fleet fields. */}
              {ws.run_state && (
                <span className="mt-0.5 flex items-center gap-1.5 text-ui-2xs">
                  <Badge variant={runStateTone(ws.run_state)} className="shrink-0 px-1.5 py-0.5">
                    {runStateLabel(ws.run_state, t)}
                  </Badge>
                  {ws.needs_you && (
                    <span className="shrink-0 font-medium text-status-warning">
                      {t('workspaces.fleet.answerNeeded')}
                    </span>
                  )}
                  {ws.running_for_seconds !== null && ws.running_for_seconds !== undefined && (
                    <span className="shrink-0 tabular-nums text-ink-faint">
                      {t('workspaces.fleet.runningFor', {
                        duration: formatDuration(ws.running_for_seconds * 1000),
                      })}
                    </span>
                  )}
                  {ws.last_event?.kind === 'file' && ws.last_event.text && (
                    <span className="min-w-0 truncate text-ink-faint">
                      {t('workspaces.fleet.touched')}{' '}
                      <span className="font-mono" dir="ltr">
                        {ws.last_event.text}
                      </span>
                    </span>
                  )}
                </span>
              )}
              {/* The path is the identity on disk; a truncated one keeps the full text
                  in `title`, because a reviewer matches the tail of the id. */}
              <span
                className="mt-0.5 block truncate font-mono text-ui-2xs text-ink-faint/70"
                title={ws.path}
                dir="ltr"
              >
                {ws.path}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
