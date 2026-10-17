'use client'

/**
 * Wave 4 — the session store gets a row.
 *
 * `POST /api/sessions/prune` landed with `core/session_lifecycle.py` and had no
 * caller: the store grew one file per REST caller and one per PWA sync, and the
 * only way to shrink it was a session at a time. This is that row, beside the
 * other session control on the settings surface — Privacy → This device clears
 * the *browser's* copy of a task; this row bounds the files on the server's
 * machine.
 *
 * The number it shows is the store's own file count (`GET /api/sessions`
 * `total`), and it says so: the row exists in the same wave as the finding that
 * `total` and the task list were two right numbers that read as a defect. `total`
 * is every JSON file, all three namespaces (the tasks a list shows, the `pwa-`
 * mirror the browser re-syncs, the `rest-` mirror of one REST caller); the task
 * count the sidebar shows is the smaller `registered_sessions`. The hint names
 * both, so a reader can reconcile them instead of seeing two numbers disagree.
 *
 * Nothing is deleted before the dry run has reported what it would free — the
 * preview is the same endpoint with `dry_run: true`, not an estimate computed
 * here — and freeing is a second, confirmed click.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database, Loader2 } from 'lucide-react'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { getSessionStore, pruneSessions, type SessionStoreView } from '@/lib/api'
import { formatBytes, formatNumber } from '@/lib/dateLocale'

/**
 * The register's own defaults for a bound that names no numbers
 * (`core/session_lifecycle.py::DEFAULT_KEEP`). Shown because they are read, not
 * because this row invented them.
 */
export const DEFAULT_KEEP_REST = 500
export const DEFAULT_KEEP_PWA = 200

/** A count the caller typed, read as a whole number of files, never negative. */
function asCount(value: string): number {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : 0
}

export function SessionStoreSection() {
  const { t, i18n } = useTranslation()
  const [store, setStore] = useState<SessionStoreView | null>(null)
  const [keepRest, setKeepRest] = useState(String(DEFAULT_KEEP_REST))
  const [keepPwa, setKeepPwa] = useState(String(DEFAULT_KEEP_PWA))
  const [wouldFree, setWouldFree] = useState<{ files: number; bytes: number } | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setStore(await getSessionStore())
    } catch {
      // Kept as null: the row says it cannot read the store, which is not "zero".
      setStore(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  function readCounts() {
    return { rest: asCount(keepRest), pwa: asCount(keepPwa) }
  }

  /** Ask the endpoint what the current counts would free. Deletes nothing. */
  async function preview() {
    setBusy(true)
    setError(null)
    setOutcome(null)
    setConfirming(false)
    const bound = readCounts()
    try {
      const r = await pruneSessions({
        keep_rest: bound.rest,
        keep_pwa: bound.pwa,
        dry_run: true,
      })
      setWouldFree({ files: r.deleted.length, bytes: r.bytes_freed })
    } catch {
      setError(t('settings.sessionStoreFailed'))
    } finally {
      setBusy(false)
    }
  }

  /** The confirmed run: this is the call that unlinks files. */
  async function apply() {
    setBusy(true)
    setError(null)
    const bound = readCounts()
    try {
      const r = await pruneSessions({
        keep_rest: bound.rest,
        keep_pwa: bound.pwa,
        dry_run: false,
      })
      const remaining = Object.values(r.remaining).reduce((a, b) => a + b, 0)
      setOutcome(
        t('settings.sessionStoreDone', {
          files: formatNumber(r.deleted.length, i18n.language),
          size: formatBytes(r.bytes_freed, i18n.language),
          remaining: formatNumber(remaining, i18n.language),
        }),
      )
      setWouldFree(null)
      setConfirming(false)
      await refresh()
    } catch {
      setError(t('settings.sessionStoreFailed'))
    } finally {
      setBusy(false)
    }
  }

  const lang = i18n.language
  const wouldFreeText =
    wouldFree === null
      ? null
      : wouldFree.files === 0
        ? t('settings.sessionStoreNothing')
        : t('settings.sessionStoreWouldFree', {
            files: formatNumber(wouldFree.files, lang),
            size: formatBytes(wouldFree.bytes, lang),
          })

  return (
    <SettingsGroup
      icon={Database}
      title={t('settings.sessionStoreGroup')}
      testid="session-store-group"
    >
      <SettingsRow
        icon={Database}
        title={t('settings.sessionStoreRow')}
        description={
          store
            ? t('settings.sessionStoreHint', {
                total: formatNumber(store.total, lang),
                tasks: formatNumber(store.registered_sessions, lang),
                size: formatBytes(store.bytes, lang),
              })
            : t('settings.sessionStoreUnreadable')
        }
        testid="session-store-row"
      >
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-end gap-3">
            <label className="flex flex-col gap-1 text-ui-xs text-ink-faint">
              {t('settings.sessionStoreKeepRest')}
              <input
                type="number"
                min={0}
                inputMode="numeric"
                value={keepRest}
                onChange={(e) => setKeepRest(e.target.value)}
                aria-label={t('settings.sessionStoreKeepRest')}
                data-testid="prune-keep-rest"
                className="w-20 rounded-lg glass-control px-2 py-1 text-ui-xs text-foreground tabular-nums"
              />
            </label>
            <label className="flex flex-col gap-1 text-ui-xs text-ink-faint">
              {t('settings.sessionStoreKeepPwa')}
              <input
                type="number"
                min={0}
                inputMode="numeric"
                value={keepPwa}
                onChange={(e) => setKeepPwa(e.target.value)}
                aria-label={t('settings.sessionStoreKeepPwa')}
                data-testid="prune-keep-pwa"
                className="w-20 rounded-lg glass-control px-2 py-1 text-ui-xs text-foreground tabular-nums"
              />
            </label>
          </div>

          {wouldFreeText ? (
            <p data-testid="prune-preview-text" className="text-ui-xs text-ink-soft text-right">
              {wouldFreeText}
            </p>
          ) : null}

          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="prune-preview"
              disabled={busy}
              onClick={() => void preview()}
              className="flex items-center gap-1.5 rounded-lg glass-control px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors hover:text-foreground disabled:opacity-50 max-lg:min-h-11"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {t('settings.sessionStorePreview')}
            </button>

            {wouldFree && wouldFree.files > 0 && !confirming ? (
              <button
                type="button"
                data-testid="prune-ask"
                disabled={busy}
                onClick={() => setConfirming(true)}
                className="rounded-lg border border-status-danger/30 bg-status-danger/15 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/25 disabled:opacity-50 max-lg:min-h-11"
              >
                {t('settings.sessionStoreAsk', {
                  files: formatNumber(wouldFree.files, lang),
                  size: formatBytes(wouldFree.bytes, lang),
                })}
              </button>
            ) : null}

            {confirming ? (
              <>
                <button
                  type="button"
                  data-testid="prune-apply"
                  disabled={busy}
                  onClick={() => void apply()}
                  className="rounded-lg border border-status-danger/30 bg-status-danger/20 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/30 disabled:opacity-50 max-lg:min-h-11"
                >
                  {t('settings.sessionStoreApply')}
                </button>
                <button
                  type="button"
                  data-testid="prune-cancel"
                  onClick={() => setConfirming(false)}
                  className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/60 transition-colors glass-control hover:text-foreground max-lg:min-h-11"
                >
                  {t('settings.cancel')}
                </button>
              </>
            ) : null}
          </div>
        </div>
      </SettingsRow>

      {outcome ? (
        <p data-testid="session-store-outcome" className="px-3 pb-2 pt-1 text-ui-xs text-ink-soft">
          {outcome}
        </p>
      ) : null}
      {error ? (
        <p
          data-testid="session-store-error"
          className="px-3 pb-2 pt-1 text-ui-xs text-status-danger"
        >
          {error}
        </p>
      ) : null}
    </SettingsGroup>
  )
}
