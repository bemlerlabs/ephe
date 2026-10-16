/**
 * Ephe — `/workspaces` (W1): the agents running in parallel, and what each one changed.
 *
 * The product showed one task and, anywhere, no change set. Past a handful of parallel
 * agents that is unusable: you cannot see who is working, on what, or whether two of them
 * are about to disagree. This page is that overview — a row per live checkout (owner,
 * state, age, path) and, per workspace, its change sets with their files, their
 * provenance and the verdicts a reviewer can file on them.
 *
 * It reads at three sizes, and the three are built, not hoped for:
 * - **none** — one calm block that says what a workspace *is*, never an error face. An
 *   empty register is a normal state.
 * - **one** — a single row beside its change sets; no filter chrome is shown because one
 *   row needs none.
 * - **twenty** — the row column scrolls, a filter narrows it, the header counts what is
 *   there, and the change-set reads run in parallel instead of one after the other.
 *
 * The reads are per workspace (`/api/change-sets?workspace_id=…`), so this page issues one
 * per live workspace and keeps a per-workspace refusal apart from the page-wide one: one
 * unreachable workspace costs its own pane, never the whole overview.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Search, TriangleAlert, X } from 'lucide-react'
import { LoadingRow, Skeleton } from '@/components/ui'
import PageHeader from '@/components/shell/PageHeader'
import WorkspaceList from '@/components/dashboard/workspaces/WorkspaceList'
import WorkspaceDetail from '@/components/dashboard/workspaces/WorkspaceDetail'
import FleetPanel from '@/components/dashboard/workspaces/FleetPanel'
import { pathConflicts } from '@/components/dashboard/workspaces/conflicts'
import { ageLabel, refusalSentence, vocabLabel } from '@/components/dashboard/workspaces/labels'
import { currentFleet, useFleet } from '@/hooks/useFleet'
import { listChangeSets, type ChangeSet } from '@/lib/api'

/** One workspace's change-set read, kept as a value so a refusal costs one pane. */
interface ChangeSetRead {
  changeSets: ChangeSet[] | undefined
  error: string
}

export default function WorkspacesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [reads, setReads] = useState<Record<string, ChangeSetRead>>({})
  const [reading, setReading] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [reload, setReload] = useState(0)

  /**
   * Re-read one workspace's change sets without touching the register.
   *
   * A verdict changes a change set — so re-reading the
   * whole register here would blank the page and unmount the pane the reviewer just acted
   * in, taking their confirmation sentence with it. The card stays mounted, the answer
   * stays on screen, and only the one workspace is read again.
   */
  const rereadWorkspace = useCallback(async (id: string) => {
    try {
      const answer = await listChangeSets(id)
      setReads((prev) => ({ ...prev, [id]: { changeSets: answer.change_sets ?? [], error: '' } }))
    } catch (error: unknown) {
      setReads((prev) => ({
        ...prev,
        [id]: { changeSets: undefined, error: refusalSentence(error) },
      }))
    }
  }, [])

  const { fleet, refresh: pollNow } = useFleet()

  /** The register as the last poll read it; null until the first answer arrives. */
  const workspaces = fleet?.workspaces ?? null
  const runs = fleet?.runs ?? []
  /** A refusal takes the page only when there is nothing behind it: a poll that failed with
   * a good answer still in hand must not blank a board that was right a moment ago. */
  const failed = Boolean(fleet?.failed && (fleet?.workspaces.length ?? 0) === 0)
  const stale = Boolean(fleet?.failed && !failed)
  const failReason = fleet?.reason ?? ''

  const refresh = useCallback(() => {
    setReload((n) => n + 1)
    pollNow()
  }, [pollNow])

  /**
   * What the register said, cut down to the part a change-set read depends on: which trees
   * are there, and what state each is in.
   *
   * The board polls on a beat and every answer moves an age, so the snapshot is a new object
   * each time. Keying the reads below on the snapshot itself would send one request per
   * workspace every three seconds for a register that did not change; keying them on this
   * line agrees with what they actually depend on.
   */
  const registerKey = useMemo(
    () => (fleet?.workspaces ?? []).map((w) => `${w.id}:${w.state}:${w.run_state ?? ''}`).join('|'),
    [fleet],
  )

  // One read per workspace, all in flight together: a serial walk over twenty workspaces
  // would make the slowest one the page's own speed.
  useEffect(() => {
    const list = currentFleet()?.workspaces ?? []
    if (list.length === 0) {
      setReads({})
      setReading(false)
      return
    }
    let cancelled = false
    setReading(true)
    Promise.all(
      list.map(async (ws): Promise<[string, ChangeSetRead]> => {
        try {
          const answer = await listChangeSets(ws.id)
          return [ws.id, { changeSets: answer.change_sets ?? [], error: '' }]
        } catch (error: unknown) {
          return [ws.id, { changeSets: undefined, error: refusalSentence(error) }]
        }
      }),
    ).then((rows) => {
      if (cancelled) return
      setReads(Object.fromEntries(rows))
      setReading(false)
    })
    return () => {
      cancelled = true
    }
  }, [registerKey, reload])

  // The selection follows the register: the first workspace while nothing is picked, and a
  // workspace that disappeared stops being the selection instead of leaving the pane empty.
  useEffect(() => {
    if (!workspaces) return
    setSelectedId((prev) =>
      prev && workspaces.some((w) => w.id === prev) ? prev : (workspaces[0]?.id ?? null),
    )
  }, [workspaces])

  const searched = useMemo(() => {
    const all = workspaces ?? []
    const needle = filter.trim().toLowerCase()
    if (!needle) return all
    return all.filter((w) =>
      [w.owner, w.branch, w.path, w.id].some((v) => (v ?? '').toLowerCase().includes(needle)),
    )
  }, [workspaces, filter])

  const counts = useMemo(() => {
    const out: Record<string, number | undefined> = {}
    for (const [id, read] of Object.entries(reads)) out[id] = read.changeSets?.length
    return out
  }, [reads])

  const owners = useMemo(
    () => Object.fromEntries((workspaces ?? []).map((w) => [w.id, w.owner])),
    [workspaces],
  )
  const conflicts = useMemo(
    () =>
      pathConflicts(
        Object.fromEntries(Object.entries(reads).map(([id, r]) => [id, r.changeSets])),
        owners,
      ),
    [reads, owners],
  )

  // The pane shows what the list shows: a filter that hides the picked workspace must not
  // leave its change sets standing on the right.
  const shown = searched.find((w) => w.id === selectedId) ?? searched[0] ?? null
  const shownRead = shown ? reads[shown.id] : undefined
  const filtered = Boolean(filter.trim())

  return (
    <div className="h-dvh overflow-y-auto" data-testid="workspaces-page">
      <div className="mx-auto w-full max-w-[1400px] px-6 py-8">
        {/* Its own root space without a sidebar — the same exit `/memory` and
            `/artifacts` carry, because the desktop has no browser back button. */}
        <button
          type="button"
          onClick={() => navigate('/chat')}
          data-testid="workspaces-back"
          className="mb-4 -ml-1.5 inline-flex min-h-7 items-center gap-1.5 rounded-md px-1.5 text-ui-xs text-ink-faint transition-colors hover:text-foreground max-lg:min-h-11 focus-ring"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          {t('workspaces.back')}
        </button>

        <PageHeader
          title={t('workspaces.title')}
          subtitle={t('workspaces.subtitle')}
          actions={
            workspaces && workspaces.length > 0 ? (
              <p className="text-ui-xs text-ink-faint" data-testid="workspaces-count">
                {t('workspaces.count', { count: workspaces.length })}
              </p>
            ) : undefined
          }
        />

        {/* The board: which runs exist, what each is doing, who needs a person. It sits above
            the register because "who needs me" is the question a page about parallel work
            answers first; the list below is the same read, seen as checkouts. */}
        <FleetPanel runs={runs} selectedId={shown?.id ?? null} onSelect={setSelectedId} />

        {stale && (
          <p
            role="status"
            data-testid="workspaces-stale"
            className="mt-3 text-ui-xs text-status-warning"
          >
            {t('workspaces.stale')}
          </p>
        )}

        {/* A cross-workspace collision is the one thing this page can say that no single
            workspace can: two agents are changing the same path right now. */}
        {conflicts.length > 0 && (
          <div
            role="status"
            data-testid="workspaces-conflicts"
            className="mt-4 rounded-lg border border-status-warning/30 bg-status-warning/10 p-3"
          >
            <p className="flex items-start gap-2 text-ui-xs text-status-warning">
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>{t('workspaces.conflicts', { count: conflicts.length })}</span>
            </p>
            <ul className="mt-1.5 space-y-0.5 pl-5.5">
              {conflicts.slice(0, 5).map((c) => (
                <li key={c.path} className="text-ui-2xs text-ink-soft">
                  <span className="font-mono" dir="ltr">
                    {c.path}
                  </span>
                  <span className="text-ink-faint">
                    {' — '}
                    {t('workspaces.conflictHolders', {
                      owners: c.holders
                        .map((h) =>
                          t('workspaces.conflictHolder', {
                            owner: h.owner,
                            state: vocabLabel('changeSetState', h.state, t),
                            when: ageLabel(h.landedAt || h.since, t),
                          }),
                        )
                        .join(', '),
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {workspaces === null ? (
          <div className="mt-6 space-y-2" data-testid="workspaces-loading">
            <LoadingRow label={t('workspaces.loading')} className="px-1" />
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-14 rounded-md" />
            ))}
          </div>
        ) : failed ? (
          <div
            role="alert"
            data-testid="workspaces-error"
            className="flex flex-col items-center gap-2 py-12 text-center text-ui-xs text-status-warn"
          >
            <p>{t('workspaces.failed')}</p>
            {failReason && (
              <p
                data-testid="workspaces-error-reason"
                className="max-w-[52ch] break-words text-ink-faint"
              >
                {failReason}
              </p>
            )}
            <button
              type="button"
              onClick={refresh}
              data-testid="workspaces-retry"
              className="inline-flex min-h-7 items-center rounded-lg border border-hairline px-3 py-1.5 font-medium text-foreground transition-colors hover:bg-surface max-lg:min-h-11 focus-ring"
            >
              {t('agentPanel.retry')}
            </button>
          </div>
        ) : workspaces.length === 0 ? (
          <div
            data-testid="workspaces-empty"
            className="mt-6 flex flex-col items-center gap-3 rounded-lg border border-dashed border-hairline px-6 py-14 text-center"
          >
            <p className="text-ui-sm font-medium text-foreground/90">
              {t('workspaces.emptyTitle')}
            </p>
            <p className="max-w-[60ch] text-ui-xs text-ink-faint">{t('workspaces.emptyBody')}</p>
            <button
              type="button"
              onClick={() => navigate('/chat')}
              data-testid="workspaces-empty-action"
              className="mt-1 inline-flex min-h-7 items-center rounded-lg border border-hairline px-3 py-1.5 text-ui-xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-11 focus-ring"
            >
              {t('workspaces.emptyAction')}
            </button>
          </div>
        ) : (
          <>
            {/* One row needs no filter; twenty do. The field appears with the second
                workspace and stays out of the way at one. */}
            {workspaces.length > 1 && (
              <div className="mt-5 mb-3 flex flex-wrap items-center gap-2">
                <div className="relative min-w-56 flex-1">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
                  <input
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder={t('workspaces.filterPlaceholder')}
                    aria-label={t('workspaces.filterPlaceholder')}
                    data-testid="workspaces-filter"
                    className="w-full rounded-lg border border-hairline bg-surface py-2 pl-8 pr-8 text-ui-sm text-foreground/80 placeholder:text-ink-faint focus-ring max-lg:min-h-11 max-lg:pr-11 max-lg:text-ui-input"
                  />
                  {filter && (
                    <button
                      type="button"
                      onClick={() => setFilter('')}
                      aria-label={t('workspaces.filterClear')}
                      title={t('workspaces.filterClear')}
                      data-testid="workspaces-filter-clear"
                      className="absolute inset-y-0 right-0 flex items-center rounded-r-lg px-2 text-ink-faint transition-colors hover:text-foreground focus-ring max-lg:w-11 max-lg:justify-center max-lg:px-0"
                    >
                      <X className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
              <div className="min-w-0">
                {searched.length === 0 ? (
                  <div className="py-10 text-center" data-testid="workspaces-nomatch">
                    <p className="px-2 text-ui-xs text-ink-faint">
                      {t('workspaces.nomatchHidden', { count: workspaces.length })}
                    </p>
                    <button
                      type="button"
                      onClick={() => setFilter('')}
                      data-testid="workspaces-clear-filter"
                      className="mt-3 min-h-7 rounded-lg border border-hairline px-3 text-ui-xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-11 focus-ring"
                    >
                      {t('workspaces.clearFilter')}
                    </button>
                  </div>
                ) : (
                  <WorkspaceList
                    workspaces={searched}
                    selectedId={shown?.id ?? null}
                    onSelect={setSelectedId}
                    counts={counts}
                  />
                )}
              </div>
              <div className="min-w-0">
                {shown ? (
                  <WorkspaceDetail
                    key={shown.id}
                    workspace={shown}
                    changeSets={shownRead?.changeSets}
                    conflicts={conflicts}
                    error={shownRead?.error ?? ''}
                    reading={reading}
                    onChanged={() => void rereadWorkspace(shown.id)}
                    onRetry={refresh}
                  />
                ) : (
                  <p
                    data-testid="workspaces-none-selected"
                    className="flex h-full min-h-[18rem] items-center justify-center rounded-lg border border-dashed border-hairline p-6 text-center text-ui-xs text-ink-faint"
                  >
                    {filtered ? t('workspaces.nomatch') : t('workspaces.emptyTitle')}
                  </p>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
