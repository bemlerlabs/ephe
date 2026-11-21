import { useState } from 'react'
import { ChevronRight, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/**
 * B2 (persona audit 2026-10-10): the transcript holds one kind of message that is
 * not a turn of the conversation — a `system` row, written by the client's own
 * compaction: the working-memory ledger of the older turns, or the note that
 * compaction happened. Before this the bubble printed it with Ephe's avatar,
 * `data-role="assistant"` and no word about what it is, so a reader met 654
 * characters of Ephe's internal state as if it were the answer to their question.
 *
 * The block stays reachable and stays labelled. It opens collapsed when the body
 * carries more than one line, because a ledger runs to COMPACT_MAX_SUMMARY_CHARS
 * (3600) and nobody reads past it; the one-line compaction note stays open.
 */
export default function SystemContextBlock({ text }: { text: string }) {
  const { t } = useTranslation()
  const multiLine = text.includes('\n')
  const [open, setOpen] = useState(!multiLine)
  return (
    <div data-testid="system-context-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        data-testid="system-context-toggle"
        className="flex items-center gap-1.5 text-ui-xs text-ink-soft hover:text-foreground/60 transition-colors"
      >
        <Layers className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
        <ChevronRight
          className={`h-3 w-3 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        />
        <span>{t('chat.systemContext')}</span>
        {multiLine && (
          <span className="font-mono text-ink-faint">
            · {t('chat.systemContextSize', { chars: text.length })}
          </span>
        )}
      </button>
      {open && (
        <p
          data-testid="system-context-body"
          className="ml-5 mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-ui-xs leading-relaxed text-ink-faint"
        >
          {text}
        </p>
      )}
    </div>
  )
}
