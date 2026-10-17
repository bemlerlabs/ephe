/**
 * Ephe — one workspace in full (W1): where it sits, what it is doing, and the change
 * sets it produced.
 *
 * The three readings a reader can land on here are kept apart on purpose: still reading,
 * could not be read, and read-and-empty. They used to collapse into one sentence each
 * time the other half was refactored, and "no change sets" is the one of the three that
 * must never stand in for the other two.
 */
import { useTranslation } from 'react-i18next'
import { Badge, LoadingRow, Skeleton } from '@/components/ui'
import type { ChangeSet, Workspace } from '@/lib/api'
import ChangeSetCard from './ChangeSetCard'
import { AgeText } from './WorkspaceList'
import type { PathConflict } from './conflicts'
import { setConflicts } from './conflicts'
import { vocabLabel, workspaceStateTone } from './labels'

export default function WorkspaceDetail({
  workspace,
  changeSets,
  conflicts,
  error,
  reading,
  onChanged,
  onRetry,
}: {
  workspace: Workspace
  /** `undefined` while the read is in flight; `[]` means read and empty. */
  changeSets: ChangeSet[] | undefined
  /** The page's cross-workspace rows; each card picks out its own. */
  conflicts: PathConflict[]
  /** The refusal sentence when this workspace's change sets could not be read. */
  error: string
  reading: boolean
  onChanged: () => void
  onRetry: () => void
}) {
  const { t } = useTranslation()

  return (
    <section
      className="min-w-0"
      data-testid="workspace-detail"
      aria-label={workspace.owner || workspace.id}
    >
      <header className="flex flex-wrap items-start gap-2 border-b border-hairline pb-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-ui-sm font-medium text-foreground/90">
            {workspace.owner || workspace.id}
          </h2>
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-ui-2xs text-ink-faint">
            <span className="truncate font-mono text-ink-soft" title={workspace.path} dir="ltr">
              {workspace.path}
            </span>
            {workspace.branch && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">{workspace.branch}</span>
              </>
            )}
            <span aria-hidden="true">·</span>
            <span className="tabular-nums" data-testid="workspace-detail-age">
              <AgeText iso={workspace.created_at} />
            </span>
          </p>
        </div>
        <Badge variant={workspaceStateTone(workspace.state)} className="shrink-0 px-2 py-0.5">
          {vocabLabel('state', workspace.state, t)}
        </Badge>
      </header>

      {error ? (
        <div
          role="alert"
          data-testid="changesets-error"
          className="flex flex-col items-start gap-2 py-8 text-ui-xs text-status-warn"
        >
          <p>{t('workspaces.changeSetsFailed')}</p>
          <p
            className="max-w-[52ch] break-words text-ink-faint"
            data-testid="changesets-error-reason"
          >
            {error}
          </p>
          <button
            type="button"
            onClick={onRetry}
            data-testid="changesets-retry"
            className="inline-flex min-h-7 items-center rounded-lg border border-hairline px-3 py-1.5 font-medium text-foreground transition-colors hover:bg-surface max-lg:min-h-11 focus-ring"
          >
            {t('agentPanel.retry')}
          </button>
        </div>
      ) : reading && changeSets === undefined ? (
        <div className="space-y-2 py-4" data-testid="changesets-loading">
          <LoadingRow label={t('workspaces.changeSetsLoading')} className="px-1" />
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      ) : (changeSets?.length ?? 0) === 0 ? (
        <div className="py-10 text-center" data-testid="changesets-empty">
          <p className="mx-auto max-w-[52ch] text-ui-xs text-ink-faint">
            {t('workspaces.changeSetsNone')}
          </p>
        </div>
      ) : (
        <div className="mt-3 space-y-2.5" data-testid="changesets-list">
          {changeSets?.map((cs) => (
            <ChangeSetCard
              key={cs.id}
              changeSet={cs}
              conflicts={setConflicts(cs, conflicts)}
              onChanged={onChanged}
            />
          ))}
        </div>
      )}
    </section>
  )
}
