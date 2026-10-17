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
 * A row reads in the order a person asks: what is it (state, agent, task), why is it not
 * moving, what do I do, what did it change, how long, where. The why is derived from the
 * fields the payload carries (`state`, `last_event`) and from nothing else: `blocked` has no
 * reason field yet, so a stuck run gets the generic sentence and its last tool when there is
 * one. A cause this surface invents is worse than the gap it fills.
 *
 * Rows arrive sorted (`core.fleet.build`): waiting on a human, then blocked, then running,
 * then done, longest-running first inside each group. The panel does not re-sort — a second
 * opinion about the order is how a board and its backend start disagreeing.
 */
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight } from 'lucide-react'
import { Badge } from '@/components/ui'
import { formatDuration } from '@/lib/duration'
import type { ChangeSet, FleetRun, Workspace } from '@/lib/api'
import { ageLabel, runStateLabel, runStateTone, vocabLabel } from './labels'

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

/** Why the row is not moving. Only the fields the payload carries are read: a wait names
 * the approval it stopped on, a stuck run names its last tool when there is one — and
 * otherwise says only what `blocked` means. There is no `blocked_reason` in the API yet. */
function Why({ run }: { run: FleetRun }) {
  const { t } = useTranslation()
  if (run.state === 'waiting_on_human') {
    const tool = run.last_event?.kind === 'awaiting' ? run.last_event.text : ''
    return (
      <p
        data-testid={`fleet-why-${run.run_id}`}
        className="mt-1 flex items-start gap-1.5 text-ui-2xs text-status-warning"
      >
        <span className="min-w-0 break-words">
          {tool ? t('workspaces.fleet.whyWaitingTool', { tool }) : t('workspaces.fleet.whyWaiting')}
        </span>
      </p>
    )
  }
  if (run.state === 'blocked') {
    const tool = run.last_event?.kind === 'tool' ? run.last_event.text : ''
    return (
      <p
        data-testid={`fleet-why-${run.run_id}`}
        className="mt-1 flex items-start gap-1.5 text-ui-2xs text-status-danger"
      >
        <span className="min-w-0 break-words">
          {tool ? t('workspaces.fleet.whyBlockedTool', { tool }) : t('workspaces.fleet.whyBlocked')}
        </span>
      </p>
    )
  }
  return null
}

/** The session behind a wait. `core.fleet.wait_runs` keys it as `session:<id>`; anything
 * else has no task to open and falls back to the task surface itself. */
function sessionOf(run: FleetRun): string {
  const prefix = 'session:'
  if (!run.run_id.startsWith(prefix)) return ''
  const id = run.run_id.slice(prefix.length)
  return id && id !== 'unknown' ? id : ''
}

const ACTION_CLASS =
  'inline-flex min-h-6 items-center gap-1 rounded-md border border-hairline px-2 py-0.5 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-9 focus-ring'

/** The one thing the row asks of the reader. A wait opens its task at the existing deep
 * link; a stuck run opens the checkout it holds, or the task surface when it holds none. */
function NextAction({
  run,
  onSelect,
}: {
  run: FleetRun
  onSelect?: (workspaceId: string) => void
}) {
  const { t } = useTranslation()
  if (!run.needs_you) return null

  if (run.state === 'waiting_on_human') {
    const session = sessionOf(run)
    const to = session ? `/chat?session=${encodeURIComponent(session)}&replay=1` : '/chat'
    return (
      <Link to={to} data-testid={`fleet-action-${run.run_id}`} className={ACTION_CLASS}>
        {t('workspaces.fleet.openTask')}
        <ArrowRight className="h-3 w-3" aria-hidden="true" />
      </Link>
    )
  }

  if (run.state === 'blocked' && run.workspace_id && onSelect) {
    return (
      <button
        type="button"
        onClick={() => onSelect(run.workspace_id)}
        data-testid={`fleet-action-${run.run_id}`}
        className={ACTION_CLASS}
      >
        {t('workspaces.fleet.openWorkspace')}
        <ArrowRight className="h-3 w-3" aria-hidden="true" />
      </button>
    )
  }

  if (run.state === 'blocked') {
    return (
      <Link to="/chat" data-testid={`fleet-action-${run.run_id}`} className={ACTION_CLASS}>
        {t('workspaces.fleet.openTask')}
        <ArrowRight className="h-3 w-3" aria-hidden="true" />
      </Link>
    )
  }

  return null
}

/** The newest change set of the run's checkout, by operation. The reads belong to the page
 * (`/api/change-sets?workspace_id=…`); a workspace whose sets have not been read yet shows
 * no summary, because "none" and "not read" are different claims. */
function ChangeSummary({
  run,
  changeSets,
}: {
  run: FleetRun
  changeSets?: Record<string, ChangeSet[] | undefined>
}) {
  const { t } = useTranslation()
  if (!run.workspace_id) return null
  const sets = changeSets?.[run.workspace_id]
  if (!sets) return null

  if (sets.length === 0) {
    return (
      <p data-testid={`fleet-changes-${run.run_id}`} className="mt-1 text-ui-2xs text-ink-faint">
        {t('workspaces.fleet.noChangeSet')}
      </p>
    )
  }

  const latest = sets[0]!
  const files = latest.files ?? []
  const counts = ['create', 'modify', 'delete']
    .map((op) => ({ op, count: files.filter((file) => file.op === op).length }))
    .filter((row) => row.count > 0)
  const approval =
    latest.state === 'draft'
      ? t('workspaces.fleet.approvalNeeded')
      : latest.state === 'review'
        ? t('workspaces.fleet.changesRequested')
        : ''

  return (
    <p
      data-testid={`fleet-changes-${run.run_id}`}
      className="mt-1 flex flex-wrap items-center gap-x-1.5 text-ui-2xs text-ink-faint"
    >
      <span>{t('workspaces.fleet.latestChange')}</span>
      <span className="text-ink-soft">{t('workspaces.files', { count: files.length })}</span>
      {counts.length > 0 && (
        <span>
          {counts
            .map((row) =>
              t('workspaces.opCount', { count: row.count, op: vocabLabel('op', row.op, t) }),
            )
            .join(' · ')}
        </span>
      )}
      {approval && (
        <span
          className={
            latest.state === 'draft'
              ? 'font-medium text-status-warning'
              : 'font-medium text-ink-soft'
          }
        >
          {approval}
        </span>
      )}
    </p>
  )
}

export default function FleetPanel({
  runs,
  workspaces = [],
  changeSets,
  selectedId,
  onSelect,
}: {
  runs: FleetRun[]
  /** The register, for the checkout's own clock. A run names its tree by id only. */
  workspaces?: Workspace[]
  /** Change sets the page has already read, keyed by workspace id. */
  changeSets?: Record<string, ChangeSet[] | undefined>
  selectedId?: string | null
  onSelect?: (workspaceId: string) => void
}) {
  const { t } = useTranslation()
  if (runs.length === 0) return null
  const needsYou = runs.filter((run) => run.needs_you).length
  const checkoutSince = new Map(workspaces.map((ws) => [ws.id, ws.created_at]))

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
          const classes = `w-full rounded-md px-2.5 py-2 text-left transition-colors ${
            selected ? 'bg-brand/10' : 'hover:bg-surface'
          } ${
            run.state === 'waiting_on_human'
              ? 'border-l-2 border-status-warning'
              : run.state === 'blocked'
                ? 'border-l-2 border-status-danger/60'
                : 'border-l-2 border-transparent'
          }`
          const heading = (
            <span className="flex items-center gap-2">
              <Badge variant={runStateTone(run.state)} className="shrink-0 px-2 py-0.5">
                {runStateLabel(run.state, t)}
              </Badge>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-ui-xs font-medium">{run.agent}</span>
                {run.task && (
                  <span className="block truncate text-ui-2xs text-ink-faint">{run.task}</span>
                )}
              </span>
            </span>
          )
          const checkoutAt = run.workspace_id ? checkoutSince.get(run.workspace_id) : ''
          const checkoutAge = checkoutAt ? ageLabel(checkoutAt, t) : ''
          // A needs-you row already names its last tool in the why sentence; the last touch
          // stays useful there when it is a file, and on every other row it is the activity.
          const showTouch = !run.needs_you || run.last_event?.kind === 'file'
          return (
            <li key={run.run_id}>
              <div data-testid={`fleet-run-${run.run_id}`} className={classes}>
                <span className="flex items-start gap-2">
                  {selectable ? (
                    <button
                      type="button"
                      onClick={() => onSelect?.(run.workspace_id)}
                      data-testid={`fleet-select-${run.run_id}`}
                      aria-current={selected ? 'true' : undefined}
                      className="min-w-0 flex-1 rounded text-left focus-ring"
                    >
                      {heading}
                    </button>
                  ) : (
                    <span className="min-w-0 flex-1">{heading}</span>
                  )}
                  {run.needs_you && (
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
                  )}
                </span>

                <Why run={run} />
                <div className="mt-1">
                  <NextAction run={run} onSelect={onSelect} />
                </div>
                <ChangeSummary run={run} changeSets={changeSets} />

                <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-ui-2xs text-ink-faint">
                  {showTouch && <LastTouch run={run} />}
                  {run.running_for_seconds !== null && run.running_for_seconds !== undefined && (
                    <Stamp>
                      {t('workspaces.fleet.runClock', {
                        duration: formatDuration(run.running_for_seconds * 1000),
                      })}
                    </Stamp>
                  )}
                  {checkoutAge && (
                    <Stamp>{t('workspaces.fleet.checkoutClock', { duration: checkoutAge })}</Stamp>
                  )}
                </span>

                {run.path ? (
                  <span
                    className="mt-0.5 block truncate font-mono text-ui-2xs text-ink-faint/70"
                    title={run.path}
                    dir="ltr"
                  >
                    {run.path}
                  </span>
                ) : (
                  <span className="mt-0.5 block text-ui-2xs text-ink-faint">
                    {t('workspaces.fleet.noCheckout')}
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
