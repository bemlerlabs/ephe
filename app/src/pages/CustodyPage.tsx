/**
 * Ephe — one change set's chain of custody.
 *
 * A diff says what changed. It cannot say who is allowed to sign it, or whether the bytes
 * on disk are still the bytes that were signed. Those two are the record's whole point, and
 * this page is where they are read: `GET /api/change-sets/{id}/custody` answers both live
 * and states the refusal `POST …/publish` would answer with before it is asked for.
 *
 * The page makes each answer *earned* rather than asserted. The signature stop is a button
 * that files the forbidden verdict for real — the author signing their own work — so the
 * refusal on screen is the gate's own sentence, not this page's opinion, and the list of
 * agents who can sign appears as the fix that sentence offers. The bytes stop compares two
 * digests character by character and marks where they part.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, GitCommitHorizontal, SquarePen, Tally5 } from 'lucide-react'
import { Badge, LoadingRow, Skeleton } from '@/components/ui'
import { CustodySeal } from '@/components/brand/CustodySeal'
import PageHeader from '@/components/shell/PageHeader'
import { getCustody, reviewChangeSet, type Custody } from '@/lib/api'
import {
  refusalSentence,
  changeSetStateTone,
  diffPrefix,
  vocabLabel,
} from '@/components/dashboard/workspaces/labels'

/** Where two digests part: the shared head, and what each side carries after it. */
/** Where two digests stop agreeing: the shared head, both tails, and the character. */
export function fork(a: string, b: string): {
  head: string
  aTail: string
  bTail: string
  index: number
} {
  let i = 0
  while (i < a.length && i < b.length && a[i] === b[i]) i += 1
  return { head: a.slice(0, i), aTail: a.slice(i), bTail: b.slice(i), index: i }
}

function Step({ index, label, children }: { index: number; label: string; children: ReactNode }) {
  return (
    <li className="flex gap-3" data-testid={`custody-step-${index}`}>
      <span
        aria-hidden="true"
        className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-hairline font-mono text-ui-2xs text-ink-faint"
      >
        {index}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-ui-2xs font-medium uppercase tracking-wide text-ink-faint">{label}</p>
        <div className="mt-1 min-w-0">{children}</div>
      </div>
    </li>
  )
}

export default function CustodyPage() {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const [custody, setCustody] = useState<Custody | null>(null)
  const [failed, setFailed] = useState('')
  const [reading, setReading] = useState(true)
  const [trying, setTrying] = useState(false)
  const [refused, setRefused] = useState('')

  const read = useCallback(async () => {
    setReading(true)
    setFailed('')
    try {
      setCustody(await getCustody(id))
    } catch (error: unknown) {
      setCustody(null)
      setFailed(refusalSentence(error))
    } finally {
      setReading(false)
    }
  }, [id])

  useEffect(() => {
    void read()
  }, [read])

  /** File the verdict the gate exists to turn down, and show what it answers. */
  async function signAsAuthor() {
    if (!custody) return
    const first = custody.files[0]?.path ?? ''
    setTrying(true)
    setRefused('')
    try {
      await reviewChangeSet(custody.change_set.id, {
        verdict: 'approve',
        reviewer: custody.author,
        reasons: [{ path: first, line: 1, why: t('custody.tryReason') }],
      })
      // A gate that let this through would be the defect; re-reading shows whatever it did.
      setRefused(t('custody.accepted'))
    } catch (error: unknown) {
      setRefused(refusalSentence(error))
    } finally {
      setTrying(false)
      void read()
    }
  }

  if (reading && custody === null) {
    return (
      <div className="space-y-3" data-testid="custody-loading">
        <LoadingRow label={t('custody.loading')} />
        <Skeleton className="h-40 rounded-lg" />
      </div>
    )
  }

  if (custody === null) {
    return (
      <div className="space-y-3" data-testid="custody-failed">
        <p className="text-ui-xs text-status-warning">{t('custody.unknown')}</p>
        {failed && <p className="max-w-[60ch] break-words text-ui-2xs text-ink-faint">{failed}</p>}
        <Link
          to="/workspaces"
          className="inline-flex min-h-7 items-center gap-1 text-ui-2xs text-ink-soft underline-offset-2 hover:underline focus-ring"
        >
          {t('custody.back')}
        </Link>
      </div>
    )
  }

  const { change_set: changeSet, files, approval, refusal } = custody
  const why = changeSet.provenance?.why || t('custody.whyMissing')

  return (
    <div className="space-y-5" data-testid="custody-page" data-change-set={changeSet.id}>
      <Link
        to="/workspaces"
        data-testid="custody-back"
        className="inline-flex min-h-7 items-center gap-1.5 text-ui-2xs text-ink-faint transition-colors hover:text-foreground focus-ring"
      >
        <ArrowLeft className="h-3 w-3" aria-hidden="true" />
        {t('custody.back')}
      </Link>

      <header className="border-b border-hairline pb-3">
        <p className="text-ui-2xs font-medium uppercase tracking-wide text-ink-faint">
          {t('custody.title')}
        </p>
        <div className="mt-1.5">
          <PageHeader
            title={changeSet.summary || t('workspaces.changeSetNoSummary')}
            subtitle={changeSet.id}
            actions={
              <Badge variant={changeSetStateTone(changeSet.state)} className="shrink-0 px-2 py-0.5">
                {vocabLabel('changeSetState', changeSet.state, t)}
              </Badge>
            }
          />
        </div>
      </header>

      {/* The sentence a session would otherwise take with it. */}
      <section aria-label={t('custody.why')}>
        <p className="text-ui-2xs font-medium uppercase tracking-wide text-ink-faint">
          {t('custody.why')}
        </p>
        <p className="mt-1 max-w-[70ch] text-ui-sm text-foreground/90" data-testid="custody-why">
          {why}
        </p>
      </section>

      <ol className="space-y-4" data-testid="custody-chain">
        <Step index={1} label={t('custody.stepAuthored')}>
          <p className="flex flex-wrap items-center gap-1.5 text-ui-xs text-ink-soft">
            <GitCommitHorizontal
              className="h-3.5 w-3.5 shrink-0 text-ink-faint"
              aria-hidden="true"
            />
            <span className="font-mono" data-testid="custody-author" dir="ltr">
              {custody.author || t('custody.noAuthor')}
            </span>
          </p>
        </Step>

        <Step index={2} label={t('custody.stepSigned')}>
          {approval ? (
            <div data-testid="custody-signature">
              <p className="text-ui-xs text-ink-soft">
                {t('custody.signedBy', { name: approval.reviewer })}
              </p>
              <ul className="mt-1 space-y-1">
                {(approval.reasons ?? []).map((reason) => (
                  <li
                    key={`${reason.path}:${reason.line}`}
                    className="flex flex-wrap items-baseline gap-1.5 text-ui-2xs"
                  >
                    <span className="font-mono text-ink-soft" dir="ltr">
                      {reason.path}:{reason.line}
                    </span>
                    <span className="min-w-0 break-words text-ink-faint">{reason.why}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-ui-xs text-ink-faint" data-testid="custody-unsigned">
              {t('custody.unsigned', { name: custody.author })}
            </p>
          )}
        </Step>

        <Step index={3} label={t('custody.stepLanded')}>
          {refusal ? (
            <div data-testid="custody-refusal">
              <p className="flex flex-wrap items-center gap-1.5">
                <Badge variant="destructive" className="shrink-0 px-1.5 py-0 font-mono">
                  {refusal.code}
                </Badge>
              </p>
              <p
                className="mt-1.5 max-w-[70ch] break-words text-ui-sm text-status-warning"
                data-testid="custody-refusal-sentence"
              >
                {refusal.sentence}
              </p>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <CustodySeal />
              <p className="text-ui-sm text-status-success" data-testid="custody-landable">
                {t('custody.canLand', { name: approval?.reviewer ?? '' })}
              </p>
            </div>
          )}
        </Step>
      </ol>

      {/* The bytes, read live. */}
      <section aria-label={t('custody.bytes')} data-testid="custody-bytes">
        <p className="text-ui-2xs font-medium uppercase tracking-wide text-ink-faint">
          {t('custody.bytes')}
        </p>
        {!custody.checked && (
          <p className="mt-1 text-ui-2xs text-ink-faint" data-testid="custody-unchecked">
            {t('custody.unchecked')}
          </p>
        )}
        <ul className="mt-2 space-y-1.5">
          {files.length === 0 && (
            <li className="text-ui-2xs text-ink-faint">{t('workspaces.filesNone')}</li>
          )}
          {files.map((file) => {
            const digests = fork(
              diffPrefix(file.recorded, 64),
              diffPrefix(file.current ?? '', 64),
            )
            return (
            <li key={file.path} data-testid={`custody-file-${file.path}`}>
              <div className="flex flex-wrap items-center gap-1.5 text-ui-2xs">
                <span className="min-w-0 flex-1 truncate font-mono text-foreground/80" dir="ltr">
                  {file.path}
                </span>
                <Badge
                  variant={file.moved ? 'destructive' : 'outline'}
                  className="shrink-0 px-1.5 py-0"
                  data-testid={`custody-mark-${file.path}`}
                >
                  {file.moved ? t('custody.moved') : t('custody.matches')}
                </Badge>
              </div>
              <div className="mt-0.5 space-y-0.5 pl-0.5 font-mono text-ui-2xs" dir="ltr">
                <p className="flex flex-wrap items-baseline gap-1.5">
                  <span className="w-14 shrink-0 text-ink-faint/70">{t('custody.recorded')}</span>
                  <span className="break-all">
                    {file.moved && file.current !== null ? (
                      <>
                        <span className="text-status-success/90">{digests.head}</span>
                        <mark className="bg-transparent text-status-danger">{digests.aTail}</mark>
                      </>
                    ) : (
                      <span className="text-ink-faint">{diffPrefix(file.recorded, 64)}</span>
                    )}
                  </span>
                </p>
                {file.moved && file.current !== null && (
                  <p
                    className="flex flex-wrap items-baseline gap-1.5"
                    data-testid={`custody-drift-${file.path}`}
                  >
                    <span className="w-14 shrink-0 text-ink-faint/70">{t('custody.onDisk')}</span>
                    <span className="break-all">
                      <span className="text-status-success/90">{digests.head}</span>
                      <mark className="bg-transparent text-status-danger">{digests.bTail}</mark>
                      <span
                        className="ml-2 tabular-nums text-ink-faint"
                        data-testid="custody-fork-index"
                      >
                        {t('custody.forkAt', { index: digests.index })}
                      </span>
                    </span>
                  </p>
                )}
              </div>
            </li>
            )
          })}
        </ul>
      </section>

      {/* The stop that cannot be argued with, and the fix it names. */}
      <section
        className="rounded-lg border border-hairline bg-surface/40 p-3"
        data-testid="custody-stops"
      >
        <p className="flex items-center gap-1.5 text-ui-2xs font-medium uppercase tracking-wide text-ink-faint">
          <SquarePen className="h-3 w-3" aria-hidden="true" />
          {t('custody.signatureStop')}
        </p>
        <p className="mt-1 max-w-[70ch] text-ui-xs text-ink-soft">
          {t('custody.signatureRule', { name: custody.author })}
        </p>

        <button
          type="button"
          onClick={() => void signAsAuthor()}
          disabled={trying || !custody.author}
          data-testid="custody-try-sign"
          className="mt-2 inline-flex min-h-7 items-center gap-1.5 rounded-md border border-control px-2.5 py-1 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground disabled:opacity-50 max-lg:min-h-11 focus-ring"
        >
          {trying ? t('custody.trying') : t('custody.tryAs', { name: custody.author })}
        </button>

        {refused && (
          <p
            role="status"
            data-testid="custody-try-refusal"
            className="mt-2.5 max-w-[70ch] break-words border-l-2 border-status-danger pl-2.5 text-ui-sm text-status-warning"
          >
            {refused}
          </p>
        )}

        <p className="mt-3 flex items-center gap-1.5 text-ui-2xs font-medium uppercase tracking-wide text-ink-faint">
          <Tally5 className="h-3 w-3" aria-hidden="true" />
          {t('custody.canSign')}
        </p>
        <p className="mt-1 text-ui-2xs text-ink-soft" data-testid="custody-custodians">
          {custody.custodians.length === 0
            ? t('custody.canSignNone')
            : t('custody.canSignCount', { count: custody.custodians.length })}
        </p>
        {custody.custodians.length > 0 && (
          <ul className="mt-1 flex flex-wrap gap-1.5" data-testid="custody-custodian-list">
            {custody.custodians.map((name) => (
              <li
                key={name}
                className="rounded-md border border-hairline px-1.5 py-0.5 font-mono text-ui-2xs text-ink-soft"
                dir="ltr"
              >
                {name}
              </li>
            ))}
          </ul>
        )}

        <button
          type="button"
          onClick={() => void read()}
          disabled={reading}
          data-testid="custody-check-again"
          className="mt-3 inline-flex min-h-7 items-center rounded-md border border-control px-2.5 py-1 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground disabled:opacity-50 max-lg:min-h-11 focus-ring"
        >
          {reading ? t('custody.checking') : t('custody.checkAgain')}
        </button>
      </section>
    </div>
  )
}
