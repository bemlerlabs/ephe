import { AlertTriangle, CheckCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { CitationCheckState } from '@/types'

/**
 * Wave 3 (web intake): the verdict a research turn's answer carries.
 *
 * The server checked the model's own sentences against the run's evidence. This
 * card states the count and names the sentences no stored source carried; it
 * never blocks or rewrites the answer, because the turn already ran.
 */
export function CitationCheck({ check }: { check?: CitationCheckState }) {
  const { t } = useTranslation()
  if (!check || check.checked === 0) return null
  const missing = Math.max(0, check.checked - check.verified)
  const complete = missing === 0
  return (
    <div
      data-testid="citation-check"
      data-verdict={complete ? 'verified' : 'unverified'}
      role="status"
      className={`mt-2 min-w-0 max-w-full rounded-lg border px-2.5 py-1.5 ${
        complete
          ? 'border-status-success/30 bg-status-success/10'
          : 'border-status-warning/40 bg-status-warning/10'
      }`}
    >
      <div className="flex min-w-0 items-start gap-1.5">
        {complete ? (
          <CheckCheck className="mt-0.5 h-3 w-3 shrink-0 text-status-success" aria-hidden="true" />
        ) : (
          <AlertTriangle
            className="mt-0.5 h-3 w-3 shrink-0 text-status-warning"
            aria-hidden="true"
          />
        )}
        <span className="min-w-0 break-words text-ui-2xs text-ink-soft">
          {complete
            ? t('chat.research.citationAll', { checked: check.checked })
            : t('chat.research.citationMissing', {
                missing,
                checked: check.checked,
              })}
        </span>
      </div>
      {!complete && check.unverified.length > 0 && (
        <ul className="m-0 mt-1 list-none space-y-0.5 p-0">
          {check.unverified.map((claim, index) => (
            <li
              key={`${index}-${claim.slice(0, 24)}`}
              className="min-w-0 break-words border-l border-status-warning/40 pl-2 text-ui-2xs text-ink-faint line-clamp-2"
            >
              {claim}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
