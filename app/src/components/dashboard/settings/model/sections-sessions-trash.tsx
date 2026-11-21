'use client'

/**
 * Chat trash — the row beside the store a delete came out of.
 *
 * `core/session_trash.py` holds a sidebar delete in a run folder instead of
 * unlinking it; this is the other half: what waits, the button that brings one
 * back, and the one button that deletes finally. Emptying shows the endpoint's
 * own dry-run numbers before it frees anything — the same rule the store row
 * above follows: the number is the endpoint's, never an estimate computed here.
 *
 * The list is newest-run-first as `GET /api/sessions/trash` answers it, and it
 * stays verbatim: namespace prefixes and all, because a restore posts the id
 * back unchanged and a prettified one would restore nothing. A row whose
 * registry row carried no title names itself by its id — the id is the only
 * fact about the session that survives the move.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { Eraser, Loader2, RotateCcw, Trash2 } from 'lucide-react'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import {
  ApiError,
  emptySessionTrash,
  listSessionTrash,
  restoreTrashedSession,
  type SessionTrashEntry,
  type TrashEmptyResult,
} from '@/lib/api'
import { dateLocaleFor, formatBytes, formatNumber } from '@/lib/dateLocale'
import { useChatStore } from '@/store/chatStore'

/** `trashed_at` dates the move; a run whose manifest never landed carries the
 *  empty string, and the row shows a dash rather than an invented "now". */
function trashedLabel(iso: string, language: string): string {
  if (!iso || Number.isNaN(Date.parse(iso))) return '—'
  return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: dateLocaleFor(language) })
}

/** The endpoint's own numbers, verified as they arrive: an answer without its
 *  list of sessions and its byte count is unreadable, and the caller decides
 *  whether unreadable is quiet (a listing) or named (a dry run about to free). */
function isTrashEmptyResult(r: TrashEmptyResult | null): r is TrashEmptyResult {
  return !!r && Array.isArray(r.deleted) && typeof r.bytes_freed === 'number'
}

export function SessionTrashSection() {
  const { t, i18n } = useTranslation()
  const [entries, setEntries] = useState<SessionTrashEntry[] | null>(null)
  const [total, setTotal] = useState(0)
  const [restoreErrors, setRestoreErrors] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)
  const [wouldEmpty, setWouldEmpty] = useState<TrashEmptyResult | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [emptyBusy, setEmptyBusy] = useState(false)
  const [emptyNote, setEmptyNote] = useState<string | null>(null)
  const [emptyRefusal, setEmptyRefusal] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const list = await listSessionTrash()
      if (!Array.isArray(list.entries) || typeof list.total !== 'number') {
        // A 200 that names neither list nor total is not an empty trash, it is
        // an answer this row cannot read, so it lands in the same state.
        throw new Error('trash list answered without its entries or total')
      }
      setEntries(list.entries)
      setTotal(list.total)
    } catch {
      // null stays: "cannot read the trash" is not "empty", and the row says which.
      setEntries(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function restore(entry: SessionTrashEntry) {
    const id = entry.session_id
    setBusyId(id)
    setRestoreErrors((errs) => {
      const next = { ...errs }
      delete next[id]
      return next
    })
    try {
      await restoreTrashedSession(id)
      await refresh()
      // The mirror file is back among the live ones; the same merge a boot runs
      // is what lets the session reappear without a reload.
      await useChatStore.getState().initFromDb()
    } catch (err) {
      // A 409 says a live session took the id while the reader was deciding.
      // The refusal's reason stays on the row — swallowing it would read as a
      // restore that silently did nothing.
      const reason = err instanceof Error && err.message ? err.message : String(err)
      setRestoreErrors((errs) => ({ ...errs, [id]: reason }))
    } finally {
      setBusyId(null)
    }
  }

  /** What an emptying would free, from the endpoint's own dry run. Frees nothing. */
  async function preview() {
    setEmptyBusy(true)
    setEmptyNote(null)
    setEmptyRefusal(null)
    setConfirming(false)
    try {
      const previewResult = await emptySessionTrash(true)
      if (!isTrashEmptyResult(previewResult)) {
        throw new Error('dry run answered without its sessions or bytes')
      }
      setWouldEmpty(previewResult)
    } catch (err) {
      setWouldEmpty(null)
      // 409 trash_empty is the empty state, not a failure worth shouting about.
      if (err instanceof ApiError && err.reasonCode === 'trash_empty') {
        setEmptyRefusal(err.message)
      } else {
        setEmptyNote(t('sessionTrash.emptyFailed'))
      }
    } finally {
      setEmptyBusy(false)
    }
  }

  /** The confirmed run: this is the call that deletes finally. */
  async function applyEmpty() {
    setEmptyBusy(true)
    try {
      const r = await emptySessionTrash(false)
      if (!isTrashEmptyResult(r)) {
        throw new Error('the emptying answered without its sessions or bytes')
      }
      setEmptyNote(
        t('sessionTrash.emptied', {
          sessions: formatNumber(r.deleted.length, i18n.language),
          size: formatBytes(r.bytes_freed, i18n.language),
        }),
      )
      setWouldEmpty(null)
      setConfirming(false)
      await refresh()
    } catch (err) {
      setWouldEmpty(null)
      setConfirming(false)
      if (err instanceof ApiError && err.reasonCode === 'trash_empty') {
        setEmptyRefusal(err.message)
      } else {
        setEmptyNote(t('sessionTrash.emptyFailed'))
      }
      await refresh()
    } finally {
      setEmptyBusy(false)
    }
  }

  const description =
    entries === null
      ? t('sessionTrash.unreadable')
      : entries.length === 0
        ? t('sessionTrash.listEmpty')
        : t('sessionTrash.hint', { count: formatNumber(total, i18n.language) })

  return (
    <SettingsGroup icon={Eraser} title={t('sessionTrash.group')} testid="session-trash-group">
      <SettingsRow
        icon={Trash2}
        title={t('sessionTrash.row')}
        description={description}
        testid="session-trash-row"
      >
        <div className="flex w-full flex-col items-end gap-2">
          {entries && entries.length > 0 ? (
            <ul data-testid="session-trash-list" className="flex w-full flex-col gap-1.5">
              {entries.map((entry) => (
                <li
                  key={`${entry.run}:${entry.session_id}`}
                  data-testid={`session-trash-item-${entry.session_id}`}
                  className="flex items-center justify-between gap-3"
                >
                  <span className="flex min-w-0 flex-col text-right lg:text-left">
                    <span className="truncate text-ui-xs text-foreground/80">
                      {entry.title ?? entry.session_id}
                    </span>
                    <span className="text-ui-xs text-ink-faint tabular-nums">
                      {trashedLabel(entry.trashed_at, i18n.language)} ·{' '}
                      {formatBytes(entry.bytes, i18n.language)}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <button
                      type="button"
                      data-testid={`session-trash-restore-${entry.session_id}`}
                      disabled={busyId !== null}
                      onClick={() => void restore(entry)}
                      className="flex items-center gap-1.5 rounded-lg glass-control px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors hover:text-foreground disabled:opacity-50 max-lg:min-h-11"
                    >
                      {busyId === entry.session_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RotateCcw className="h-3.5 w-3.5" />
                      )}
                      {t('sessionTrash.restore')}
                    </button>
                    {restoreErrors[entry.session_id] ? (
                      <p
                        data-testid={`session-trash-restore-error-${entry.session_id}`}
                        className="text-ui-xs text-status-danger"
                      >
                        {restoreErrors[entry.session_id]}
                      </p>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex items-center gap-2">
            {!wouldEmpty && !confirming ? (
              <button
                type="button"
                data-testid="trash-empty"
                disabled={emptyBusy}
                onClick={() => void preview()}
                className="flex items-center gap-1.5 rounded-lg border border-status-danger/30 bg-status-danger/15 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/25 disabled:opacity-50 max-lg:min-h-11"
              >
                {emptyBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                {t('sessionTrash.emptyButton')}
              </button>
            ) : null}

            {wouldEmpty && !confirming ? (
              <>
                <p data-testid="trash-preview" className="text-ui-xs text-ink-soft">
                  {t('sessionTrash.wouldDelete', {
                    sessions: formatNumber(wouldEmpty.deleted.length, i18n.language),
                    size: formatBytes(wouldEmpty.bytes_freed, i18n.language),
                  })}
                </p>
                <button
                  type="button"
                  data-testid="trash-empty-ask"
                  disabled={emptyBusy}
                  onClick={() => setConfirming(true)}
                  className="rounded-lg border border-status-danger/30 bg-status-danger/15 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/25 disabled:opacity-50 max-lg:min-h-11"
                >
                  {t('sessionTrash.emptyButton')}
                </button>
              </>
            ) : null}

            {confirming ? (
              <>
                <p className="text-ui-xs text-ink-soft">{t('sessionTrash.confirm')}</p>
                <button
                  type="button"
                  data-testid="trash-empty-apply"
                  disabled={emptyBusy}
                  onClick={() => void applyEmpty()}
                  className="rounded-lg border border-status-danger/30 bg-status-danger/20 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/30 disabled:opacity-50 max-lg:min-h-11"
                >
                  {emptyBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  {t('sessionTrash.emptyApply')}
                </button>
                <button
                  type="button"
                  data-testid="trash-empty-cancel"
                  onClick={() => {
                    setConfirming(false)
                    setWouldEmpty(null)
                  }}
                  className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/60 transition-colors glass-control hover:text-foreground max-lg:min-h-11"
                >
                  {t('settings.cancel')}
                </button>
              </>
            ) : null}
          </div>

          {emptyRefusal ? (
            <p data-testid="trash-empty-refusal" className="text-ui-xs text-ink-soft">
              {emptyRefusal}
            </p>
          ) : null}
          {emptyNote ? (
            <p data-testid="trash-empty-note" className="text-ui-xs text-ink-soft">
              {emptyNote}
            </p>
          ) : null}
        </div>
      </SettingsRow>
    </SettingsGroup>
  )
}
