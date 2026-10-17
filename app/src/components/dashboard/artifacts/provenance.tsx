/**
 * Ephe — the provenance of a workbench card (R4/A3).
 *
 * This is the part no product shows: not just "a file" but which assignment born
 * it, which tool call wrote it, and what that call was decided. The arguments come
 * out of the audit as an edited short text — never the hash, because 16 hex digits
 * unsalted are a confession about a file name, not a redaction, and this surface
 * can be photographed.
 *
 * The chain reads top to bottom: the task, the call that wrote the card, then the
 * tool calls the turn left in the audit. A dead read is a state of its own — an
 * endless spinner on a finished request is a lie the user waits on. `known: false`
 * is likewise a state, not an error: cards from before the chain have no turn, so
 * this row shows the gap instead of selling an empty list as "no provenance".
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { formatNumber } from '@/lib/dateLocale'
import { ExternalLink, GitCommit, RefreshCw, ShieldAlert, TriangleAlert } from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import { artifactProvenance, type ArtifactProvenance, type ArtifactProvenanceCall } from '@/lib/api'

/** Past this many audit rows the chain stops informing and starts scrolling. */
const CHAIN_LIMIT = 6

const CHIP =
  'inline-flex items-center gap-1 rounded-md border border-hairline px-1.5 py-0.5 text-ui-2xs text-ink-soft transition-colors hover:border-brand/40 hover:text-foreground'

/** One link of the chain: a node on the spine, a line of its own content. */
function ChainNode({ last = false, children }: { last?: boolean; children: ReactNode }) {
  return (
    <li className="flex gap-2" data-testid="artifact-provenance-node">
      <span aria-hidden className="relative flex w-3 flex-shrink-0 justify-center">
        <span className="mt-1 h-1.5 w-1.5 rounded-full bg-brand/50" />
        {!last && <span className="absolute bottom-[-8px] top-3 w-px bg-hairline" />}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  )
}

/** A single tool call: what ran, how it was decided, how a failure reads. */
function CallLine({ call, lang }: { call: ArtifactProvenanceCall; lang: string }) {
  const failed = Boolean(call.status) && call.status !== 'ok'
  const decided = Boolean(call.decision) && call.decision !== 'auto'
  return (
    <div className="flex items-baseline gap-2 text-ui-2xs">
      <span className="min-w-0 flex-1 truncate font-mono text-foreground/80" title={call.args}>
        {call.tool || call.kind}
        {call.args ? ` ${call.args}` : ''}
      </span>
      {failed && (
        <span
          className="flex flex-shrink-0 items-center gap-1 text-status-danger"
          title={call.status}
        >
          <TriangleAlert className="h-3 w-3" />
          {call.status}
        </span>
      )}
      {decided && (
        <span
          className="flex flex-shrink-0 items-center gap-1 text-status-warning"
          title={call.decision}
        >
          <ShieldAlert className="h-3 w-3" />
          {call.decision}
        </span>
      )}
      {typeof call.duration_ms === 'number' && (
        <span className="flex-shrink-0 tabular-nums text-ink-faint">
          {formatNumber(call.duration_ms, lang)} ms
        </span>
      )}
    </div>
  )
}

export default function ArtifactProvenanceBlock({
  id,
  onOpenTask,
}: {
  id: string
  /** R4 (A3): whoever can open the assignment links it instead of only naming it. */
  onOpenTask?: () => void
}) {
  const { t, i18n } = useTranslation()
  const [data, setData] = useState<ArtifactProvenance | null>(null)
  const [failed, setFailed] = useState(false)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setFailed(false)
    artifactProvenance(id)
      .then((r) => !cancelled && setData(r))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [id, nonce])

  const header = (
    <p className="mb-1.5 flex items-center gap-1.5 text-ui-2xs font-semibold uppercase tracking-wide text-ink-faint">
      <GitCommit className="h-3 w-3" />
      {t('artifacts.page.provenance.title')}
    </p>
  )

  if (failed) {
    return (
      <div
        className="rounded-lg border border-hairline bg-surface p-2.5"
        data-testid="artifact-provenance"
        data-state="failed"
      >
        {header}
        <p className="text-ui-xs text-ink-faint">{t('artifacts.page.provenance.failed')}</p>
        <button
          type="button"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="artifact-provenance-retry"
          className={`mt-1.5 ${CHIP}`}
        >
          <RefreshCw className="h-3 w-3" />
          {t('artifacts.page.provenance.retry')}
        </button>
      </div>
    )
  }

  if (!data) {
    return <LoadingRow label={t('artifacts.page.provenance.loading')} className="px-1" />
  }

  const shown = data.calls.slice(0, CHAIN_LIMIT)
  const rest = data.calls.length - shown.length

  return (
    <div
      className="rounded-lg border border-hairline bg-surface p-2.5"
      data-testid="artifact-provenance"
    >
      {header}
      {!data.known ? (
        <p className="text-ui-xs text-ink-faint">{t('artifacts.page.provenance.unknown')}</p>
      ) : (
        <ol className="space-y-2" data-testid="artifact-provenance-chain">
          <ChainNode>
            <p className="text-ui-xs text-foreground/80" title={data.turn_id}>
              {t('artifacts.page.provenance.turn')}{' '}
              <span className="font-mono text-brand/80">{data.turn_id}</span>
            </p>
            {data.call_id && (
              <p className="text-ui-2xs text-ink-faint" title={data.call_id}>
                {t('artifacts.page.provenance.call')}{' '}
                <span className="font-mono text-brand/80">{data.call_id}</span>
              </p>
            )}
            {onOpenTask && (
              <button
                type="button"
                onClick={onOpenTask}
                title={data.turn_id || undefined}
                data-testid="artifact-open-task"
                className={`mt-1.5 ${CHIP}`}
              >
                <ExternalLink className="h-3 w-3" />
                {t('artifacts.page.provenance.openTask')}
              </button>
            )}
          </ChainNode>

          {shown.length === 0 ? (
            <ChainNode last>
              <p className="text-ui-2xs text-ink-faint">{t('artifacts.page.provenance.noCalls')}</p>
            </ChainNode>
          ) : (
            shown.map((c, i) => (
              <ChainNode key={`${c.ts}-${i}`} last={i === shown.length - 1 && rest === 0}>
                <CallLine call={c} lang={i18n.language} />
              </ChainNode>
            ))
          )}

          {rest > 0 && (
            <ChainNode last>
              <p className="text-ui-2xs text-ink-faint" data-testid="artifact-provenance-more">
                {t('artifacts.page.provenance.more', { n: rest })}
              </p>
            </ChainNode>
          )}
        </ol>
      )}
    </div>
  )
}
