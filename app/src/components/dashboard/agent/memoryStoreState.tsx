'use client'

/**
 * B1 (persona audit 2026-10-10): the sentence for a memory store that is not
 * answering. It belongs in one file because the page and the panel tab read the
 * same store through one hook — two surfaces with two opinions about the same
 * failure is how the empty state came to stand for an outage.
 */
import { useTranslation } from 'react-i18next'

/**
 * Wave 10: the sentence for an empty trash.
 *
 * "This is where what Ephe forgot ends up" is only true when the active store
 * keeps a deleted entry at all. Under a store that deletes finally the same
 * emptiness means nothing was ever kept, and the line has to say so instead of
 * promising a recovery that cannot happen (walkthrough 2026-10-12, finding 1).
 * The store's own `detail` names the provider, so the honest case shows it; a
 * backend without the field keeps the old sentence.
 */
export function trashEmptySentence(
  supportedLine: string,
  restoreSupported: boolean,
  detail: string,
): string {
  if (restoreSupported) return supportedLine
  return detail || supportedLine
}

export function MemoryStoreUnavailable({
  reason,
  onRetry,
}: {
  reason: string
  onRetry: () => void
}) {
  const { t } = useTranslation()
  return (
    <div
      role="alert"
      data-testid="memory-unreachable"
      className="flex flex-col items-center gap-2 py-10 text-center text-ui-xs text-status-warn"
    >
      <p>{t('memory.unreachable')}</p>
      {reason && (
        <p
          data-testid="memory-unreachable-reason"
          className="max-w-[52ch] break-words font-mono text-ui-2xs text-ink-faint"
        >
          {reason}
        </p>
      )}
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg border border-control px-3 py-1.5 font-medium text-foreground transition-colors hover:bg-surface max-lg:min-h-11 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        {t('agentPanel.retry')}
      </button>
    </div>
  )
}
