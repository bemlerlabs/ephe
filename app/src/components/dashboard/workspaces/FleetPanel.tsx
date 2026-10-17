/**
 * Ephe — the fleet panel (G2): one row per run, the ones that need you first.
 *
 * Every leading product shows parallel work as a list of *threads* — what each one is doing
 * right now, and which one is blocked on the person reading the list. This is that list. A row
 * is a run, not a checkout: the same board carries the agent runs that own no tree and the
 * runs that have stopped on an unanswered approval, which is exactly the row nobody can see
 * today.
 *
 * The one distinction the surface must not blur: a run that waits on a person and a run that
 * is thinking are both alive, and every registry in the product calls both "running". Here
 * they are different words, different tones, and only one of them is a thing to do.
 *
 * Rows arrive sorted (`core.fleet.build`): waiting on a human, then blocked, then running,
 * then done, longest-running first inside each group. The panel does not re-sort — a second
 * opinion about the order is how a board and its backend start disagreeing.
 */
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui'
import { formatDuration } from '@/lib/duration'
import type { FleetRun } from '@/lib/api'
import { runStateLabel, runStateTone } from './labels'

/** What a run last touched, as a sentence fragment. */
function LastTouch({ run }: { run: FleetRun }) {
  const { t } = useTranslation()
  const event = run.last_event
  if (!event || event.kind === 'none' || !event.text) {
    return <span className="text-ink-faint">{t('workspaces.fleet.touchedNothing')}</span>
  }
  if (event.kind === 'file') {
    return (
      <span className="text-ink-soft">
        {t('workspaces.fleet.touched')}{' '}
        <span className="font-mono text-ui-2xs" dir="ltr">
          {event.text}
        </span>
      </span>
    )
  }
  if (event.kind === 'awaiting') {
    return (
      <span className="text-status-warning">
        {t('workspaces.fleet.awaitingTool', { tool: event.text })}
      </span>
    )
  }
  return (
    <span className="text-ink-soft">{t('workspaces.fleet.usedTool', { tool: event.text })}</span>
  )
}

/** One duration on a row. */
function Stamp({ children }: { children: React.ReactNode }) {
  return <span className="shrink-0 tabular-nums">{children}</span>
}

/** How long the row has been alive, in the product's own duration format — and in the tense
 * the state asks for: a finished run is not still running, and a stuck one did not finish.
 * Every key is written as a literal so the i18n gate checks it. */
function RunningFor({ run }: { run: FleetRun }) {
  const { t } = useTranslation()
  if (run.running_for_seconds === null || run.running_for_seconds === undefined) return null
  const duration = formatDuration(run.running_for_seconds * 1000)
  if (run.kind === 'session' || run.state === 'waiting_on_human') {
    return <Stamp>{t('workspaces.fleet.waitedFor', { duration })}</Stamp>
  }
  if (run.state === 'done') {
    return <Stamp>{t('workspaces.fleet.finishedIn', { duration })}</Stamp>
  }
  if (run.state === 'blocked') {
    return <Stamp>{t('workspaces.fleet.ranFor', { duration })}</Stamp>
  }
  return <Stamp>{t('workspaces.fleet.runningFor', { duration })}</Stamp>
}

/** The thing a row asks of the reader, when it asks anything. */
function NeedsYou({ run }: { run: FleetRun }) {
  const { t } = useTranslation()
  if (!run.needs_you) return null
  return (
    <span
      data-testid={`fleet-needs-you-${run.run_id}`}
      className={`shrink-0 rounded-full px-2 py-0.5 text-ui-2xs font-medium ${
        run.state === 'waiting_on_human'
          ? 'bg-status-warning/20 text-status-warning'
          : 'bg-status-danger/20 text-status-danger'
      }`}
    >
      {run.state === 'waiting_on_human'
        ? t('workspaces.fleet.answerNeeded')
        : t('workspaces.fleet.needsRestart')}
    </span>
  )
}

export default function FleetPanel({
  runs,
  selectedId,
  onSelect,
}: {
  runs: FleetRun[]
  selectedId?: string | null
  onSelect?: (workspaceId: string) => void
}) {
  const { t } = useTranslation()
  if (runs.length === 0) return null
  const needsYou = runs.filter((run) => run.needs_you).length

  return (
    <section
      aria-label={t('workspaces.fleet.title')}
      data-testid="fleet-panel"
      className="mt-5 rounded-lg border border-hairline bg-surface/40 p-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-ui-sm font-medium text-foreground/90">{t('workspaces.fleet.title')}</h2>
        <p className="text-ui-xs text-ink-faint" data-testid="fleet-summary">
          {t('workspaces.fleet.count', { count: runs.length })}
          {' · '}
          <span className={needsYou > 0 ? 'text-status-warning' : undefined}>
            {needsYou > 0
              ? t('workspaces.fleet.needsYou', { count: needsYou })
              : t('workspaces.fleet.needsYouNone')}
          </span>
        </p>
      </div>

      <ul className="mt-2.5 flex flex-col gap-1" role="list">
        {runs.map((run) => {
          const selectable = Boolean(onSelect && run.workspace_id)
          const selected = Boolean(run.workspace_id && run.workspace_id === selectedId)
          const classes = `w-full rounded-md px-2.5 py-2 text-left transition-colors focus-ring ${
            selected ? 'bg-brand/10' : 'hover:bg-surface'
          } ${
            run.state === 'waiting_on_human'
              ? 'border-l-2 border-status-warning'
              : run.state === 'blocked'
                ? 'border-l-2 border-status-danger/60'
                : 'border-l-2 border-transparent'
          }`
          const body = (
            <>
              <span className="flex items-center gap-2">
                <Badge variant={runStateTone(run.state)} className="shrink-0 px-2 py-0.5">
                  {runStateLabel(run.state, t)}
                </Badge>
                <span className="min-w-0 flex-1 truncate text-ui-xs font-medium">{run.agent}</span>
                <NeedsYou run={run} />
              </span>
              <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-ui-2xs text-ink-faint">
                <LastTouch run={run} />
                {run.path ? (
                  <span className="truncate font-mono text-ink-faint/70" title={run.path} dir="ltr">
                    {run.path}
                  </span>
                ) : (
                  <span>{t('workspaces.fleet.noCheckout')}</span>
                )}
                <RunningFor run={run} />
              </span>
            </>
          )
          return (
            <li key={run.run_id}>
              {selectable ? (
                <button
                  type="button"
                  onClick={() => onSelect?.(run.workspace_id)}
                  data-testid={`fleet-run-${run.run_id}`}
                  aria-current={selected ? 'true' : undefined}
                  className={classes}
                >
                  {body}
                </button>
              ) : (
                <div data-testid={`fleet-run-${run.run_id}`} className={classes}>
                  {body}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
