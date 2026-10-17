import { useMemo } from 'react'
import { useChatStore } from '@/store/chatStore'
import { storageFootprint } from '@/lib/storageFootprint'
import { useTranslation } from 'react-i18next'

/**
 * R44 (P3): small footprint of the IndexedDB cache — session count and JSON
 * length in MB. Best effort: with the cache missing, the pill stays off.
 *
 * P4 finding 6: the pill truncated as one whole string — what got cut was the
 * NUMBER ("48 Sitzun…"). The translated string is now split at invisible
 * separators (WORD JOINER / FUNCTION SEPARATOR): digit pieces are `shrink-0` and
 * are never shortened, the word block in between is what has to yield.
 * The words come from the locale, not from a copy in this file.
 */
const FOOTPRINT_COUNT_MARK = '⁣'
const FOOTPRINT_MB_MARK = '⁤'

export function StorageFootprint() {
  const { t: t2, i18n: i18n2 } = useTranslation()
  const sessions = useChatStore((st) => st.sessions)
  const footprint = useMemo(
    () => storageFootprint(sessions, i18n2.language),
    [sessions, i18n2.language],
  )
  const pieces = useMemo(() => {
    if (!footprint) return null
    const [count, mb] = footprint.split(' · ')
    const pattern = t2('statusBar.storage', {
      count: FOOTPRINT_COUNT_MARK,
      mb: FOOTPRINT_MB_MARK,
    })
    return pattern
      .split(/(⁣|⁤)/)
      .filter((piece) => piece.length > 0)
      .map((piece) =>
        piece === FOOTPRINT_COUNT_MARK
          ? { kind: 'num' as const, text: count }
          : piece === FOOTPRINT_MB_MARK
            ? { kind: 'num' as const, text: mb }
            : { kind: 'text' as const, text: piece },
      )
  }, [footprint, t2])
  if (!footprint || !pieces) return null
  const [count] = footprint.split(' · ')
  return (
    <span
      data-testid="statusbar-storage-chip"
      title={t2('statusBar.storageHint', { count })}
      className="flex min-w-0 items-baseline text-ui-xs font-mono tabular-nums text-ink-faint"
    >
      {pieces.map((p, i) =>
        p.kind === 'num' ? (
          <span key={i} data-testid="statusbar-storage-number" className="shrink-0 whitespace-pre">
            {p.text}
          </span>
        ) : (
          <span key={i} className="min-w-0 overflow-hidden text-ellipsis whitespace-pre">
            {p.text}
          </span>
        ),
      )}
    </span>
  )
}
