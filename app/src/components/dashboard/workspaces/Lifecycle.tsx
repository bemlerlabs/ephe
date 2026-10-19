/**
 * Ephe — the life of one change set (n1-publish).
 *
 * Before this the state was a word and nothing read it as a life: an approval left the record
 * still reading `draft`, and a set a reviewer sent back could only be replaced by building a new
 * one under a new id, which took the provenance with it. `core/change_set_lifecycle` holds the
 * loop — which states may follow which, the amend that keeps the id, the view that folds the
 * record and the ledger together — and `server/routes/workspaces.py` hands that view over beside
 * the set. This file draws it and drives the two moves a reviewer makes by hand.
 *
 * `LifecycleTrack` reads only the state the list already carries, so the line is on screen
 * without a second call. The panel reads the whole life when the card is opened, which is where
 * the located reasons behind a verdict and the moves still open are worth the round trip.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui'
import {
  amendChangeSet,
  getChangeSetLifecycle,
  moveChangeSetState,
  type ChangeSetLifecycle,
} from '@/lib/api'
import { refusalSentence, vocabLabel, withdrawLabelKey } from './labels'

/** `core/change_set_lifecycle.STATIONS` — the order a set passes them, read by eye on the card. */
const STATIONS = ['draft', 'review', 'approved', 'published']

/**
 * Where one set stands on the line, from its state alone.
 *
 * `rejected` is off the line — it is the decision reached at the review station, not a stage a
 * set moves through — so the marker holds at `review` and the badge beside it carries the word.
 */
export function LifecycleTrack({ state }: { state: string }) {
  const { t } = useTranslation()
  const found = STATIONS.indexOf(state)
  const standing = found < 0 ? STATIONS.indexOf('review') : found

  return (
    <ol
      aria-label={t('workspaces.lifecycle.track')}
      className="mt-2 flex flex-wrap items-center gap-1"
      data-testid="changeset-lifecycle-track"
    >
      {STATIONS.map((name, index) => (
        <li key={name} className="flex items-center gap-1">
          {index > 0 && (
            <span aria-hidden="true" className="text-ink-faint/40">
              ›
            </span>
          )}
          <span
            data-station={name}
            data-done={String(index <= standing)}
            data-current={String(index === standing)}
            className={`rounded px-1.5 py-0.5 text-ui-2xs ${
              index === standing
                ? 'bg-brand/10 font-medium text-foreground'
                : index < standing
                  ? 'text-ink-soft'
                  : 'text-ink-faint/60'
            }`}
          >
            {vocabLabel('changeSetState', name, t)}
          </span>
        </li>
      ))}
    </ol>
  )
}

/**
 * The whole life of one set, read when a reviewer opens its card.
 *
 * The two moves here are the ones a reviewer makes by hand: amend (read the workspace again
 * under the same id) and pull back (move the state without touching a file). A verdict comes
 * from the review form below, and a publish from the card's own button; neither is repeated.
 */
export default function LifecyclePanel({
  changeSetId,
  onChanged,
}: {
  changeSetId: string
  /** Called after a move landed, so the page re-reads the workspace and this panel re-reads. */
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const [life, setLife] = useState<ChangeSetLifecycle | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sentence, setSentence] = useState('')
  const [ok, setOk] = useState(true)

  const read = useCallback(async () => {
    setError('')
    try {
      const { lifecycle } = await getChangeSetLifecycle(changeSetId)
      setLife(lifecycle)
    } catch (err) {
      setError(refusalSentence(err) || t('workspaces.lifecycle.failed'))
    }
  }, [changeSetId, t])

  useEffect(() => {
    void read()
  }, [read])

  async function act(run: () => Promise<unknown>, done: string, refused: string) {
    setBusy(true)
    setSentence('')
    try {
      await run()
      setOk(true)
      setSentence(t(done))
      await read()
      onChanged()
    } catch (err) {
      setOk(false)
      setSentence(refusalSentence(err) || t(refused))
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <p
        role="alert"
        data-testid={`changeset-lifecycle-error-${changeSetId}`}
        className="mt-3 max-w-[52ch] break-words text-ui-2xs text-status-warning"
      >
        {t('workspaces.lifecycle.failed')} {error}
      </p>
    )
  }
  if (!life) {
    return (
      <p
        data-testid={`changeset-lifecycle-reading-${changeSetId}`}
        className="mt-3 text-ui-2xs text-ink-faint"
      >
        {t('workspaces.lifecycle.reading')}
      </p>
    )
  }

  const last = life.verdict
  const quiet = !life.amendable && life.withdraw.length === 0

  return (
    <div
      className="mt-3 rounded-md border border-hairline bg-surface/30 p-2.5"
      data-testid={`changeset-lifecycle-${changeSetId}`}
    >
      <p
        className="text-ui-2xs text-ink-soft"
        data-testid={`changeset-lifecycle-last-${changeSetId}`}
      >
        {last
          ? t('workspaces.lifecycle.lastVerdict', {
              verdict: vocabLabel('verdict', last.verdict, t),
              reviewer: last.reviewer,
            })
          : t('workspaces.lifecycle.noVerdict')}
      </p>

      {life.reasons.length > 0 && (
        <div className="mt-1.5" data-testid={`changeset-lifecycle-reasons-${changeSetId}`}>
          <p className="text-ui-2xs font-medium text-ink-faint">
            {t('workspaces.lifecycle.reasons')}
          </p>
          <ul className="mt-0.5 space-y-0.5">
            {life.reasons.map((reason) => (
              <li
                key={`${reason.path}:${reason.line}:${reason.why}`}
                className="flex flex-wrap gap-1.5 text-ui-2xs text-ink-soft"
              >
                <span className="shrink-0 font-mono text-ink-faint" dir="ltr">
                  {reason.path}:{reason.line}
                </span>
                <span className="min-w-0 break-words">{reason.why}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {life.amendable && (
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() =>
              void act(
                () => amendChangeSet(changeSetId),
                'workspaces.amend.done',
                'workspaces.amend.refused',
              )
            }
            data-testid={`changeset-amend-${changeSetId}`}
            className="min-h-7 px-2.5 py-1 text-ui-2xs max-lg:min-h-11"
          >
            {t('workspaces.amend.action')}
          </Button>
        )}
        {life.withdraw.map((state) => {
          const key = withdrawLabelKey(state)
          return key ? (
            <button
              key={state}
              type="button"
              disabled={busy}
              onClick={() =>
                void act(
                  () => moveChangeSetState(changeSetId, state),
                  'workspaces.withdraw.done',
                  'workspaces.withdraw.refused',
                )
              }
              data-testid={`changeset-withdraw-${state}-${changeSetId}`}
              className="inline-flex min-h-7 items-center rounded-md border border-control px-2.5 py-1 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground disabled:opacity-50 max-lg:min-h-11 focus-ring"
            >
              {t(key)}
            </button>
          ) : null
        })}
        {quiet && (
          <span className="text-ui-2xs text-ink-faint">{t('workspaces.lifecycle.none')}</span>
        )}
      </div>

      {sentence && (
        <p
          role="status"
          data-tone={ok ? 'ok' : 'warn'}
          data-testid={`changeset-lifecycle-sentence-${changeSetId}`}
          className={`mt-2 text-ui-2xs ${ok ? 'text-status-success' : 'text-status-warning'}`}
        >
          {sentence}
        </p>
      )}
    </div>
  )
}
