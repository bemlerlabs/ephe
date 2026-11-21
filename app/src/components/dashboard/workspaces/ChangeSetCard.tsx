/**
 * Ephe — one change set under a workspace (W1).
 *
 * The card answers the four questions a reviewer asks before deciding anything: what is
 * this (summary and state), who made it and why (provenance — `why` is the field the
 * domain will not let a session drop), what exactly changed (each file with its operation
 * and the diff digest), and what can I do with it (a verdict, then a publish).
 *
 * The review controls are collapsed until they are asked for. Twenty workspaces with
 * twenty change sets each is a list to scan, not twenty open forms.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ChevronDown,
  ChevronRight,
  GitCommitHorizontal,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react'
import { Badge, Button } from '@/components/ui'
import { publishChangeSet, type ChangeSet } from '@/lib/api'
import type { PathConflict } from './conflicts'
import {
  refusalSentence,
  ageLabel,
  changeSetStateTone,
  diffPrefix,
  opTone,
  vocabLabel,
  verdictCanMove,
} from './labels'
import LifecyclePanel, { LifecycleTrack } from './Lifecycle'
import ReviewForm from './ReviewForm'

/** The session id is long and only ever compared by eye — the head is enough. */
function shortId(value: string): string {
  return value.length > 8 ? value.slice(0, 8) : value
}

const OP_ORDER = ['create', 'modify', 'delete']

/** What the set did, before how it is recorded: files by operation. */
function Outcome({ changeSet }: { changeSet: ChangeSet }) {
  const { t } = useTranslation()
  const files = changeSet.files ?? []
  const counts = OP_ORDER.map((op) => ({
    op,
    count: files.filter((file) => file.op === op).length,
  })).filter((row) => row.count > 0)

  return (
    <p
      data-testid={`changeset-outcome-${changeSet.id}`}
      className="mt-1.5 flex flex-wrap items-center gap-x-1.5 text-ui-2xs text-ink-faint"
    >
      {files.length === 0 ? (
        <span>{t('workspaces.filesNone')}</span>
      ) : (
        <>
          <span className="font-medium text-foreground/80">
            {t('workspaces.files', { count: files.length })}
          </span>
          <span>
            {counts
              .map((row) =>
                t('workspaces.opCount', { count: row.count, op: vocabLabel('op', row.op, t) }),
              )
              .join(' · ')}
          </span>
        </>
      )}
    </p>
  )
}

/** The condition the review gate puts on this set, in the state it is in. */
function ApprovalCondition({ changeSet }: { changeSet: ChangeSet }) {
  const { t } = useTranslation()
  const author = changeSet.provenance?.agent_id ?? ''
  const other = t('workspaces.approval.other', {
    author: author || t('workspaces.approval.theAuthor'),
  })

  let sentence: string
  switch (changeSet.state) {
    case 'draft':
      sentence = t('workspaces.approval.draft', { other })
      break
    case 'review':
      sentence = t('workspaces.approval.review', { other })
      break
    case 'approved':
      sentence = t('workspaces.approval.approved')
      break
    case 'published':
      sentence = t('workspaces.approval.published')
      break
    case 'rejected':
      sentence = t('workspaces.approval.rejected')
      break
    default:
      sentence = t('workspaces.approval.pending')
  }

  return (
    <p
      data-testid={`changeset-approval-${changeSet.id}`}
      className="mt-1 text-ui-2xs text-ink-soft"
    >
      {sentence}
    </p>
  )
}

/** The digests that identify each file, listed under it. */
function Hashes({ changeSet }: { changeSet: ChangeSet }) {
  const { t } = useTranslation()
  const files = changeSet.files ?? []
  if (files.length === 0) return null
  return (
    <ul
      className="mt-1 space-y-0.5 pl-1"
      data-testid={`changeset-hashes-${changeSet.id}`}
      aria-label={t('workspaces.hashes')}
    >
      {files.map((file) => (
        <li
          key={`hash:${file.op}:${file.path}`}
          className="flex items-center gap-2 text-ui-2xs text-ink-faint/60"
        >
          <span className="min-w-0 flex-1 truncate font-mono" title={file.path} dir="ltr">
            {file.path}
          </span>
          <span className="shrink-0 font-mono" title={file.diff_sha}>
            {diffPrefix(file.diff_sha)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export default function ChangeSetCard({
  changeSet,
  conflicts,
  onChanged,
}: {
  changeSet: ChangeSet
  /** The rows of the page's conflict list this set is a holder in. */
  conflicts: PathConflict[]
  /** Called after a verdict or a publish landed, so the page re-reads the workspace. */
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [dryRun, setDryRun] = useState(true)
  const [publishing, setPublishing] = useState(false)
  const [publishSentence, setPublishSentence] = useState('')
  const [publishOk, setPublishOk] = useState(true)

  const provenance = changeSet.provenance ?? { session_id: '', agent_id: '', why: '' }
  const files = changeSet.files ?? []
  const author = provenance.agent_id

  async function publish() {
    setPublishing(true)
    setPublishSentence('')
    try {
      const { result, sentence } = await publishChangeSet(changeSet.id, { dry_run: dryRun })
      // The route answers with a sentence either way — what landed and what was rolled back
      // when it ran for real, the rehearsal's count when it did not. `result.reason` is the
      // same sentence before the route dressed it, so a route that ships without one still
      // reads as words rather than as a blank.
      setPublishOk(Boolean(result?.ok))
      setPublishSentence(
        sentence ||
          result?.reason ||
          (result?.ok ? t('workspaces.publish.done') : t('workspaces.publish.refused')),
      )
      if (result?.ok && !dryRun) onChanged()
    } catch (error) {
      setPublishOk(false)
      setPublishSentence(refusalSentence(error) || t('workspaces.publish.refused'))
    } finally {
      setPublishing(false)
    }
  }

  return (
    <article
      className="rounded-lg border border-hairline bg-surface/40 p-3"
      data-testid={`changeset-card-${changeSet.id}`}
    >
      <header className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3
            className="text-ui-xs font-medium text-foreground/90"
            data-testid={`changeset-summary-${changeSet.id}`}
          >
            {changeSet.summary || t('workspaces.changeSetNoSummary')}
          </h3>
        </div>
        <Badge variant={changeSetStateTone(changeSet.state)} className="shrink-0 px-2 py-0.5">
          {vocabLabel('changeSetState', changeSet.state, t)}
        </Badge>
      </header>

      <LifecycleTrack state={changeSet.state} />

      <Outcome changeSet={changeSet} />
      <ApprovalCondition changeSet={changeSet} />

      {/* A set that was sent back says so where its state shows, without opening the form.
          The reasons themselves are one click away, on the panel that reads the ledger. */}
      {changeSet.state === 'review' && (
        <p
          className="mt-1 text-ui-2xs text-status-warning"
          data-testid={`changeset-sentback-${changeSet.id}`}
        >
          {t('workspaces.lifecycle.sentBack')}
        </p>
      )}
      {changeSet.state === 'rejected' && (
        <p
          className="mt-1 text-ui-2xs text-status-warning"
          data-testid={`changeset-rejected-${changeSet.id}`}
        >
          {t('workspaces.lifecycle.rejectedHint')}
        </p>
      )}

      {/* Provenance sits under the outcome; the id and the session are identifiers a
          reviewer compares by eye. */}
      <p
        className="mt-2 flex flex-wrap items-baseline gap-1.5 text-ui-2xs text-ink-soft"
        data-testid={`changeset-provenance-${changeSet.id}`}
      >
        <GitCommitHorizontal
          className="h-3 w-3 shrink-0 self-center text-ink-faint"
          aria-hidden="true"
        />
        <span className="min-w-0 break-words">
          {provenance.why || t('workspaces.provenanceEmpty')}
        </span>
      </p>
      <p className="mt-0.5 flex flex-wrap items-center gap-1.5 pl-4.5 font-mono text-ui-2xs text-ink-faint">
        <span data-testid={`changeset-id-${changeSet.id}`} className="text-ink-faint/70">
          {changeSet.id}
        </span>
        {author && <span aria-hidden="true">·</span>}
        {author && <span>{author}</span>}
        {author && provenance.session_id && <span aria-hidden="true">·</span>}
        {provenance.session_id && (
          <span title={provenance.session_id}>{shortId(provenance.session_id)}</span>
        )}
      </p>

      {files.length > 0 && (
        <ul className="mt-2 space-y-0.5" data-testid={`changeset-files-${changeSet.id}`}>
          {files.map((file) => (
            <li
              key={`${file.op}:${file.path}`}
              className="flex items-center gap-2 px-1 text-ui-2xs"
            >
              <Badge variant={opTone(file.op)} className="shrink-0 px-1.5 py-0">
                {vocabLabel('op', file.op, t)}
              </Badge>
              <span
                className="min-w-0 flex-1 truncate font-mono text-foreground/80"
                title={file.path}
                dir="ltr"
              >
                {file.path}
              </span>
            </li>
          ))}
        </ul>
      )}

      <Hashes changeSet={changeSet} />

      {/* The run's own surface. The page-wide strip says two workspaces collide somewhere;
          this card says it is *this* set, on *this* path, and names the run it will meet —
          before the publish, where a collision is still a decision. */}
      {conflicts.length > 0 && (
        <div
          role="status"
          data-testid={`changeset-conflict-${changeSet.id}`}
          className="mt-2 rounded-md border border-status-warning/30 bg-status-warning/10 px-2 py-1.5"
        >
          <ul className="space-y-0.5 text-ui-2xs text-status-warning">
            {conflicts.map((row) => (
              <li key={row.path} className="flex items-start gap-1.5">
                <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="min-w-0 break-words">
                  {t('workspaces.conflictWarning', {
                    path: row.path,
                    holders: row.holders
                      .filter((h) => h.changeSetId !== changeSet.id)
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

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <Link
          to={`/workspaces/change/${encodeURIComponent(changeSet.id)}`}
          data-testid={`changeset-custody-${changeSet.id}`}
          className="inline-flex min-h-7 items-center gap-1 rounded-md border border-control px-2.5 py-1 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-11 focus-ring"
        >
          <ShieldCheck className="h-3 w-3" aria-hidden="true" />
          {t('workspaces.custodyAction')}
        </Link>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          data-testid={`changeset-review-open-${changeSet.id}`}
          className="inline-flex min-h-7 items-center gap-1 rounded-md border border-control px-2.5 py-1 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-11 focus-ring"
        >
          {open ? (
            <ChevronDown className="h-3 w-3" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3 w-3" aria-hidden="true" />
          )}
          {t('workspaces.review.action')}
        </button>

        <label className="inline-flex min-h-7 items-center gap-1.5 px-1 text-ui-2xs text-ink-faint max-lg:min-h-11">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            data-testid={`changeset-dryrun-${changeSet.id}`}
            className="accent-brand"
          />
          {t('workspaces.publish.dryRun')}
        </label>

        <Button
          type="button"
          variant={dryRun ? 'secondary' : 'primary'}
          disabled={publishing}
          onClick={() => void publish()}
          data-testid={`changeset-publish-${changeSet.id}`}
          className="min-h-7 px-3 py-1 text-ui-2xs max-lg:min-h-11"
        >
          {dryRun ? t('workspaces.publish.check') : t('workspaces.publish.apply')}
        </Button>
      </div>

      {open && (
        <>
          <LifecyclePanel changeSetId={changeSet.id} onChanged={onChanged} />
          {/* A verdict only moves a draft, a set in review or an approved one. A rejected set
              is amended and a published one has shipped, so neither is offered a form whose
              answer would change nothing. */}
          {verdictCanMove(changeSet.state) && (
            <ReviewForm
              changeSetId={changeSet.id}
              files={files}
              author={author}
              onDone={() => onChanged()}
            />
          )}
        </>
      )}

      {publishSentence && (
        <p
          role="status"
          data-testid={`changeset-publish-sentence-${changeSet.id}`}
          data-tone={publishOk ? 'ok' : 'warn'}
          className={`mt-2 text-ui-2xs ${publishOk ? 'text-status-success' : 'text-status-warning'}`}
        >
          {publishSentence}
        </p>
      )}
    </article>
  )
}
