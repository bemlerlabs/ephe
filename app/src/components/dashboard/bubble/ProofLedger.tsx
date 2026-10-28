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
        return (
          <li
            key={run.id}
            data-testid={`proof-run-${run.id}`}
            data-ok={ok}
            className={`tabular-nums text-ui-2xs ${ok ? 'text-ink-soft' : 'text-status-danger'}`}
          >
            {audience === 'expert'
              ? t('chat.ledger.run', {
                  tool: run.name,
                  args: argPreview(run.args),
                  state: t(ok ? 'chat.ledger.passed' : 'chat.ledger.failed'),
                  ms: Math.round(run.duration_ms ?? 0),
                  digest: run.sha256 ? run.sha256.slice(0, 8) : '—',
                })
              : t(ok ? 'chat.proof.everyday' : 'chat.proof.failed', { seconds })}
          </li>
        )
      })}
    </ul>
  )
}

/** The one value a reader needs to tell two runs of the same tool apart. */
function argPreview(args: Record<string, unknown> | undefined): string {
  const value = Object.values(args ?? {}).find((item) => typeof item === 'string')
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  return text.length > 40 ? `${text.slice(0, 40)}…` : text
}
