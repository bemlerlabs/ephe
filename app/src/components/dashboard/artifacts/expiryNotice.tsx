/**
 * Ephe — the expiry question (R4/A4, ownership rule 2026-10-06).
 *
 * Workbench copies expire after 30 days. **Expiry is a question here, not a
 * process:** this row only counts what has reached its deadline, and two answers
 * carry the decision away (`answerArtifactExpiry`). There is no background branch
 * that deletes without an answer — and no asking a third time: "keep" stops the
 * clock for that card.
 *
 * One card or several: the selection decides how many an answer concerns.
 * Deleting demands the second confirmation at the very same place.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock, TriangleAlert } from 'lucide-react'
import { answerArtifactExpiry, listArtifactExpiry, type ArtifactExpiry } from '@/lib/api'
import { formatBytes } from '@/lib/dateLocale'

const ACTION_BUTTON =
  'rounded-md px-2 py-1 text-ui-xs font-medium transition-colors min-h-7 disabled:opacity-50'

export default function ArtifactExpiryNotice({
  active,
  onAnswered,
}: {
  active: boolean
  onAnswered?: () => void
}) {
  const { t, i18n } = useTranslation()
  const [expiry, setExpiry] = useState<ArtifactExpiry | null>(null)
  const [unchecked, setUnchecked] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState<'keep' | 'delete' | null>(null)

  const refresh = useCallback(() => {
    listArtifactExpiry()
      .then((r) => {
        setExpiry(r)
        setUnchecked([])
        setConfirming(false)
      })
      .catch(() => setExpiry(null))
  }, [])

  useEffect(() => {
    if (!active) return
    refresh()
  }, [active, refresh])

  if (!active || !expiry || expiry.due.length === 0) return null

  const due = expiry.due
  const chosen = due.filter((a) => !unchecked.includes(a.id))
  const chosenIds = chosen.map((a) => a.id)

  async function answer(action: 'keep' | 'delete') {
    if (chosenIds.length === 0) return
    setLastAction(action)
    setBusy(true)
    setFailed(null)
    try {
      await answerArtifactExpiry(chosenIds, action)
      setOpen(false)
      onAnswered?.()
      refresh()
    } catch (e) {
      // The answer was lost, not the file — this row says that too.
      setFailed(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="rounded-lg border border-hairline bg-surface px-2.5 py-2 text-ui-xs"
      data-testid="artifact-expiry"
      role="group"
      aria-label={t('artifacts.expiry.group')}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <Clock className="h-3.5 w-3.5 text-status-warning flex-shrink-0" aria-hidden />
        <span className="text-foreground/80 min-w-0">
          {t('artifacts.expiry.question', {
            count: due.length,
            days: expiry.days,
            size: formatBytes(expiry.bytes, i18n.language),
          })}
        </span>
        <span className="flex-1" />
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          data-testid="expiry-choose"
          className={`${ACTION_BUTTON} text-ink-soft hover:text-foreground/80`}
        >
          {t('artifacts.expiry.choose', { count: chosen.length, total: due.length })}
        </button>
        <button
          onClick={() => void answer('keep')}
          disabled={busy || chosenIds.length === 0}
          className={`${ACTION_BUTTON} bg-brand/20 text-brand hover:bg-brand/20`}
          data-testid="expiry-keep"
        >
          {t('artifacts.expiry.keep')}
        </button>
        {confirming ? (
          <span className="flex items-center gap-1.5">
            <TriangleAlert className="h-3.5 w-3.5 text-destructive" aria-hidden />
            <span className="text-foreground/80">{t('artifacts.expiry.confirm')}</span>
            <button
              onClick={() => void answer('delete')}
              disabled={busy}
              className={`${ACTION_BUTTON} border border-destructive/40 text-destructive hover:bg-surface`}
              data-testid="expiry-delete-yes"
            >
              {t('artifacts.expiry.deleteYes', { count: chosenIds.length })}
            </button>
            <button
              onClick={() => setConfirming(false)}
              className={`${ACTION_BUTTON} text-ink-soft hover:text-foreground/80`}
            >
              {t('artifacts.expiry.cancel')}
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            disabled={busy || chosenIds.length === 0}
            className={`${ACTION_BUTTON} text-destructive hover:bg-surface`}
            data-testid="expiry-delete"
          >
            {t('artifacts.expiry.delete')}
          </button>
        )}
      </div>

      {open && (
        <ul className="mt-1.5 space-y-0.5 border-t border-hairline pt-1.5">
          {due.map((a) => (
            <li key={a.id} className="flex items-center gap-2">
              <label className="flex min-w-0 flex-1 items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!unchecked.includes(a.id)}
                  onChange={(e) =>
                    setUnchecked((prev) =>
                      e.target.checked ? prev.filter((id) => id !== a.id) : [...prev, a.id],
                    )
                  }
                  className="accent-brand"
                />
                <span className="truncate text-foreground/80">{a.name}</span>
              </label>
              <span className="text-ink-faint tabular-nums">
                {formatBytes(a.size, i18n.language)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {failed && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-destructive">
          <p role="alert">
            {t('artifacts.expiry.failed')}: {failed}
          </p>
          {lastAction && (
            <button
              type="button"
              onClick={() => void answer(lastAction)}
              disabled={busy}
              data-testid="expiry-retry"
              className={`${ACTION_BUTTON} border border-destructive/40 hover:bg-surface`}
            >
              {t('agentPanel.retry')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
