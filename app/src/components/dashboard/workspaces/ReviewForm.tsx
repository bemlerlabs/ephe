/**
 * Ephe — filing a verdict on one change set (W1).
 *
 * The review gate is strict in two ways that shape this form, and both are worth
 * repeating here rather than letting a reviewer learn them from a refusal:
 *
 * - every verdict needs at least one *located* reason — a path, a line above zero and
 *   the sentence a reviewer would say (`core/review_gate.Reason`). There is no verdict
 *   without one, not even an approval, so the reason is not an optional comment field.
 * - a reason must name a file the change set actually touches, and the author cannot
 *   approve their own work. The path control is therefore a select over the set's own
 *   files, and the author is named next to the reviewer field.
 *
 * The outcome is always a sentence. A refusal that arrives as an `ApiError` is read
 * through `serverErrorText` (the code's own translation) with the server's sentence as
 * the fallback, so a reader never meets a bare status number.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2 } from 'lucide-react'
import { Badge, Button } from '@/components/ui'
import { reviewChangeSet, type FileChange, type Verdict } from '@/lib/api'
import { refusalSentence } from './labels'

/** The reviewer's name is remembered between verdicts — typing it each time is friction
 * that buys nothing, and the value is not a secret. */
const REVIEWER_KEY = 'ephe.reviewer'

interface DraftReason {
  /** Local identity only, so removing a middle row does not re-key the ones below it. */
  key: number
  path: string
  line: number
  why: string
}

let nextKey = 1

function draftReason(path: string): DraftReason {
  return { key: nextKey++, path, line: 1, why: '' }
}

function storedReviewer(): string {
  try {
    return window.localStorage.getItem(REVIEWER_KEY) ?? ''
  } catch {
    return ''
  }
}

export default function ReviewForm({
  changeSetId,
  files,
  author,
  onDone,
}: {
  changeSetId: string
  files: FileChange[]
  /** The agent that authored the set; approving it as them is refused by the gate. */
  author: string
  onDone: (verdict: Verdict, reviewer: string) => void
}) {
  const { t } = useTranslation()
  const firstPath = files[0]?.path ?? ''
  const [reviewer, setReviewer] = useState(storedReviewer)
  const [reasons, setReasons] = useState<DraftReason[]>(() => [draftReason(firstPath)])
  const [busy, setBusy] = useState<Verdict | null>(null)
  const [sentence, setSentence] = useState('')
  const [tone, setTone] = useState<'ok' | 'warn'>('ok')

  const patch = (key: number, next: Partial<DraftReason>) =>
    setReasons((rows) => rows.map((r) => (r.key === key ? { ...r, ...next } : r)))

  async function submit(verdict: Verdict) {
    const named = reviewer.trim()
    const clean = reasons.map((r) => ({
      path: r.path,
      line: Math.floor(Number(r.line)),
      why: r.why.trim(),
    }))
    // The gate's own rule, checked here first: a verdict needs one reason naming a path
    // and a line above zero, and the reviewer needs a name.
    if (!named || clean.length === 0 || clean.some((r) => !r.path || !(r.line >= 1) || !r.why)) {
      setTone('warn')
      setSentence(t('workspaces.review.needReason'))
      return
    }
    setBusy(verdict)
    setSentence('')
    try {
      const answer = await reviewChangeSet(changeSetId, {
        verdict,
        reviewer: named,
        reasons: clean,
      })
      const who = answer?.verdict?.reviewer || named
      try {
        window.localStorage.setItem(REVIEWER_KEY, named)
      } catch {
        /* private mode — the verdict stands, only the convenience is lost */
      }
      setTone('ok')
      setSentence(t(`workspaces.review.done.${verdict}`, { reviewer: who }))
      onDone(verdict, who)
    } catch (error) {
      setTone('warn')
      // A refusal is a sentence; when the thrown value carries none, this surface says so
      // in its own words rather than leaving the reviewer without an answer.
      setSentence(refusalSentence(error) || t('workspaces.review.refused'))
    } finally {
      setBusy(null)
    }
  }

  const authoredByReviewer = Boolean(author) && reviewer.trim() === author

  return (
    <div
      className="mt-2 rounded-lg border border-hairline bg-surface/40 p-2.5"
      data-testid={`review-form-${changeSetId}`}
    >
      <label className="block text-ui-2xs text-ink-faint">
        {t('workspaces.review.reviewer')}
        <input
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          placeholder={t('workspaces.review.reviewerPlaceholder')}
          data-testid={`review-reviewer-${changeSetId}`}
          className="mt-1 w-full rounded-md border border-hairline bg-surface px-2 py-1.5 text-ui-xs text-foreground/80 placeholder:text-ink-faint focus-ring max-lg:min-h-11 max-lg:text-ui-input"
        />
      </label>
      {authoredByReviewer && (
        <p
          className="mt-1 text-ui-2xs text-status-warning"
          data-testid={`review-author-${changeSetId}`}
        >
          {t('workspaces.review.authorWarn', { author })}
        </p>
      )}

      <div className="mt-2 space-y-1.5" data-testid={`review-reasons-${changeSetId}`}>
        {reasons.map((r) => (
          <div key={r.key} className="flex flex-wrap items-start gap-1.5">
            <label className="sr-only" htmlFor={`review-path-${changeSetId}-${r.key}`}>
              {t('workspaces.review.path')}
            </label>
            <select
              id={`review-path-${changeSetId}-${r.key}`}
              value={r.path}
              onChange={(e) => patch(r.key, { path: e.target.value })}
              data-testid={`review-path-${changeSetId}-${r.key}`}
              title={t('workspaces.review.path')}
              className="min-w-40 flex-1 rounded-md border border-hairline bg-surface px-2 py-1.5 font-mono text-ui-2xs text-foreground/80 focus-ring max-lg:min-h-11 max-lg:text-ui-input"
            >
              {files.length === 0 && <option value="">{t('workspaces.review.noFiles')}</option>}
              {files.map((f) => (
                <option key={f.path} value={f.path}>
                  {f.path}
                </option>
              ))}
            </select>
            <label className="sr-only" htmlFor={`review-line-${changeSetId}-${r.key}`}>
              {t('workspaces.review.line')}
            </label>
            <input
              id={`review-line-${changeSetId}-${r.key}`}
              type="number"
              min={1}
              value={r.line}
              onChange={(e) => patch(r.key, { line: Number(e.target.value) })}
              title={t('workspaces.review.line')}
              data-testid={`review-line-${changeSetId}-${r.key}`}
              className="w-16 rounded-md border border-hairline bg-surface px-2 py-1.5 text-ui-2xs tabular-nums text-foreground/80 focus-ring max-lg:min-h-11 max-lg:text-ui-input"
            />
            <label className="sr-only" htmlFor={`review-why-${changeSetId}-${r.key}`}>
              {t('workspaces.review.why')}
            </label>
            <input
              id={`review-why-${changeSetId}-${r.key}`}
              value={r.why}
              onChange={(e) => patch(r.key, { why: e.target.value })}
              placeholder={t('workspaces.review.whyPlaceholder')}
              data-testid={`review-why-${changeSetId}-${r.key}`}
              className="min-w-44 flex-[3] rounded-md border border-hairline bg-surface px-2 py-1.5 text-ui-xs text-foreground/80 placeholder:text-ink-faint focus-ring max-lg:min-h-11 max-lg:text-ui-input"
            />
            <button
              type="button"
              onClick={() => setReasons((rows) => rows.filter((row) => row.key !== r.key))}
              disabled={reasons.length === 1}
              aria-label={t('workspaces.review.removeReason')}
              title={t('workspaces.review.removeReason')}
              data-testid={`review-remove-${changeSetId}-${r.key}`}
              className="min-h-7 min-w-7 rounded-md p-1.5 text-ink-faint transition-colors hover:text-foreground disabled:opacity-40 max-lg:min-h-11 max-lg:min-w-11 focus-ring"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => setReasons((rows) => [...rows, draftReason(firstPath)])}
          data-testid={`review-add-${changeSetId}`}
          className="inline-flex min-h-7 items-center gap-1 rounded-md px-1.5 text-ui-2xs text-ink-soft transition-colors hover:text-foreground max-lg:min-h-11 focus-ring"
        >
          <Plus className="h-3 w-3" aria-hidden="true" />
          {t('workspaces.review.addReason')}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {(['approve', 'request_changes', 'reject'] as const).map((verdict) => (
          <Button
            key={verdict}
            type="button"
            variant={
              verdict === 'reject' ? 'destructive' : verdict === 'approve' ? 'primary' : 'secondary'
            }
            disabled={busy !== null}
            onClick={() => void submit(verdict)}
            data-testid={`review-submit-${changeSetId}-${verdict}`}
            className="min-h-7 px-3 py-1.5 text-ui-2xs max-lg:min-h-11"
          >
            {t(`workspaces.verdict.${verdict}`)}
          </Button>
        ))}
      </div>

      {sentence && (
        <p
          role="status"
          data-testid={`review-sentence-${changeSetId}`}
          data-tone={tone}
          className={`mt-2 flex items-start gap-1.5 text-ui-2xs ${
            tone === 'warn' ? 'text-status-warning' : 'text-status-success'
          }`}
        >
          <Badge variant={tone === 'warn' ? 'warning' : 'success'} className="shrink-0 px-1.5 py-0">
            {t('workspaces.review.decision')}
          </Badge>
          <span className="min-w-0 break-words">{sentence}</span>
        </p>
      )}
    </div>
  )
}
