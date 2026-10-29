import { useTranslation } from 'react-i18next'
import { useDeepSelect } from '@/lib/deepSettings'
import { audienceOf } from '@/lib/proofAudience'
import type { ToolCall } from '@/types'

/**
 * E1: the earned proof of one turn, directly above the answer. Every run that
 * finished is listed with its duration and the digest of the payload the reader
 * holds, so the claim can be re-hashed from either side.
 */
export function ProofLedger({ tools }: { tools: readonly ToolCall[] }) {
  const { t } = useTranslation()
  const audience = audienceOf(useDeepSelect('chat.details_mode', 'expanded'))
  const runs = tools.filter((run) => run.status === 'completed' || run.status === 'failed')
  if (runs.length === 0) return null

  return (
    <ul data-testid="proof-ledger" className="mb-1.5 space-y-0.5">
      {runs.map((run) => {
        const ok = run.status === 'completed'
        const seconds = ((run.duration_ms ?? 0) / 1000).toFixed(1)
        const line =
          audience === 'expert'
            ? t('chat.ledger.run', {
                tool: run.name,
                args: argPreview(run.args),
                state: t(ok ? 'chat.ledger.passed' : 'chat.ledger.failed'),
                ms: Math.round(run.duration_ms ?? 0),
                digest: run.sha256 ? run.sha256.slice(0, 8) : '—',
              })
            : t(ok ? 'chat.proof.everyday' : 'chat.proof.failed', { seconds })
        return (
          <li
            key={run.id}
            data-testid={`proof-run-${run.id}`}
            data-ok={ok}
            className={`tabular-nums text-ui-2xs ${ok ? 'text-ink-soft' : 'text-status-danger'}`}
          >
            {/* E1: the line is the claim; the payload the frame delivered is the
                proof behind it. A run whose frame carried no result has nothing
                to open and stays a plain line. */}
            {run.result ? (
              <details data-testid={`proof-details-${run.id}`}>
                <summary className="cursor-pointer">{line}</summary>
                <pre
                  data-testid={`proof-result-${run.id}`}
                  className="mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap text-ui-2xs text-ink-soft"
                >
                  {clipResult(run.result)}
                </pre>
              </details>
            ) : (
              line
            )}
          </li>
        )
      })}
    </ul>
  )
}

/** The proof stays readable: the frame's first 2000 characters, with the cut named. */
function clipResult(result: string): string {
  return result.length > 2000 ? `${result.slice(0, 2000)}\n… (${result.length} chars)` : result
}

/** The one value a reader needs to tell two runs of the same tool apart. */
function argPreview(args: Record<string, unknown> | undefined): string {
  const value = Object.values(args ?? {}).find((item) => typeof item === 'string')
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  return text.length > 40 ? `${text.slice(0, 40)}…` : text
}
