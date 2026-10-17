'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RotateCw, Loader2 } from 'lucide-react'
import { getAudit, type AuditEntry } from '@/lib/api'
import {
  AUDIT_KINDS,
  AUDIT_PAGE_LIMIT,
  auditClock,
  auditDayKey,
  auditDayLabel,
  auditDuration,
  auditErrorCode,
  auditKindName,
  auditNumber,
  auditSignature,
  auditZoneLabel,
  type AuditPayload,
} from './auditFormat'

// ── R23: audit tab — append-only tool/approval history (read-only) ───────
// R2-H: the row carries the four pieces tabTipAudit promises — tool, signature
// short form, duration, outcome.
// N1 (this wave): plus a time basis (local clock + zone abbreviation), day groups,
// the event kind as its own piece, a filter that covers the whole schema, the
// count of items ("80 of N"), an error that is not an empty log, and a loading
// state where hanging can be told apart from success.

export function AuditTab() {
  const { t, i18n } = useTranslation()
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  const [totalMatching, setTotalMatching] = useState<number | null>(null)
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)
  const [error, setError] = useState<{ message: string; code: string } | null>(null)
  const [pending, setPending] = useState(false)
  const [kindFilter, setKindFilter] = useState('')
  // Only the newest request's answer may write — otherwise a filter error
  // arriving late would overwrite the list currently on screen.
  const seq = useRef(0)

  const load = useCallback(() => {
    const mine = ++seq.current
    setPending(true)
    getAudit(AUDIT_PAGE_LIMIT, kindFilter)
      .then((raw) => {
        if (mine !== seq.current) return
        const r = raw as unknown as AuditPayload
        if (!Array.isArray(r.entries)) {
          // An incomplete answer is an error, not an "empty".
          setError({ message: '', code: '' })
          return
        }
        setEntries(r.entries)
        setTotalMatching(typeof r.total_matching === 'number' ? r.total_matching : null)
        setUpdatedAt(Date.now())
        setError(null)
      })
      .catch((err: unknown) => {
        if (mine !== seq.current) return
        const message = err instanceof Error ? err.message : String(err)
        // The last good list stays on screen: a 500 must not look like an emptied
        // evidence log.
        setError({ message, code: auditErrorCode(message) })
      })
      .finally(() => {
        if (mine === seq.current) setPending(false)
      })
  }, [kindFilter])

  useEffect(() => {
    load()
  }, [load])

  const groups = useMemo(() => {
    const out: { day: string; rows: { e: AuditEntry; i: number }[] }[] = []
    ;(entries ?? []).forEach((e, i) => {
      const day = auditDayKey(e.ts)
      const last = out[out.length - 1]
      if (last && last.day === day) last.rows.push({ e, i })
      else out.push({ day, rows: [{ e, i }] })
    })
    return out
  }, [entries])

  // useTranslation does not hand back an i18n everywhere (test mocks of the panel
  // wiring): '' falls back to the browser locale inside the Intl helpers — an
  // evidence tab must never be the thing that crashes.
  const lang = i18n?.language ?? ''
  const zone = entries === null ? '' : auditZoneLabel(lang)
  const shown = entries?.length ?? 0
  const countLine =
    totalMatching === null
      ? t('agentPanel.auditCountNoTotal', { shown: auditNumber(shown, lang) })
      : t('agentPanel.auditCount', {
          shown: auditNumber(shown, lang),
          total: auditNumber(totalMatching, lang),
        })

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div
        className="px-3 py-2 flex flex-wrap items-center gap-1.5 border-b border-hairline flex-shrink-0"
        role="group"
        aria-label={t('agentPanel.auditFilter')}
      >
        {['', ...AUDIT_KINDS].map((k) => (
          <button
            key={k || 'all'}
            onClick={() => setKindFilter(k)}
            aria-pressed={kindFilter === k}
            data-kind={k || 'all'}
            title={k || undefined}
            className={`px-2 py-0.5 rounded-md text-ui-xs font-medium transition-colors ${
              kindFilter === k
                ? 'bg-brand/20 text-brand'
                : 'text-ink-faint hover:bg-surface hover:text-foreground/80'
            }`}
          >
            {k ? auditKindName(k, t) : t('agentPanel.auditAll')}
          </button>
        ))}
        <span className="flex-1" />
        <button
          onClick={load}
          aria-label={t('agentPanel.auditRefresh')}
          aria-busy={pending}
          data-testid="audit-refresh"
          className="p-1.5 rounded-md text-ink-faint hover:text-foreground hover:bg-surface transition-colors"
        >
          {pending ? (
            <Loader2 data-testid="audit-refresh-spinner" className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RotateCw className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {entries !== null && (
        <div className="px-3 py-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 border-b border-hairline text-ui-2xs text-ink-faint flex-shrink-0">
          {zone && (
            <span data-testid="audit-time-basis">{t('agentPanel.auditTimeBasis', { zone })}</span>
          )}
          <span data-testid="audit-count">{countLine}</span>
          {updatedAt !== null && (
            <span data-testid="audit-updated">
              {t('agentPanel.auditUpdated', {
                time: auditClock(new Date(updatedAt).toISOString()),
              })}
            </span>
          )}
        </div>
      )}

      {error && (
        <div
          role="alert"
          data-testid="audit-error"
          className="mx-2 mt-2 rounded-lg border border-status-danger/40 bg-status-danger/10 px-2 py-1.5 space-y-1 flex-shrink-0"
        >
          <p className="text-ui-xs text-status-danger flex items-center gap-2">
            <span>{t('agentPanel.auditLoadFailed')}</span>
            {error.code && <span className="font-mono">HTTP {error.code}</span>}
          </p>
          {error.message && (
            <p className="text-ui-2xs text-ink-faint truncate" title={error.message}>
              {error.message}
            </p>
          )}
          {entries !== null && (
            <p className="text-ui-2xs text-ink-faint">{t('agentPanel.auditKeptLastList')}</p>
          )}
          <button
            type="button"
            onClick={load}
            data-testid="audit-error-retry"
            className="rounded-md border border-hairline bg-surface px-2 py-0.5 text-ui-2xs text-foreground/80 hover:text-foreground transition-colors"
          >
            {t('agentPanel.retry')}
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {entries === null && !error ? (
          <Loader2 className="h-4 w-4 animate-spin text-brand/50" />
        ) : entries === null ? null : shown === 0 ? (
          <p className="text-ui-xs text-ink-faint px-1">{t('agentPanel.auditEmpty')}</p>
        ) : (
          groups.map((g) => (
            <div key={g.day || 'ohne-Zeitstempel'}>
              {g.day && (
                <div
                  data-testid="audit-day-heading"
                  className="sticky top-0 z-10 bg-surface/95 px-2 py-1 text-ui-2xs font-medium text-ink-faint"
                >
                  {auditDayLabel(g.day, lang)}
                </div>
              )}
              {g.rows.map(({ e, i }) => (
                <div
                  data-testid="audit-entry-row"
                  key={`${e.ts}-${i}`}
                  className="flex items-start gap-2 rounded-lg px-2 py-1.5 text-ui-xs hover:bg-surface"
                >
                  {/* WP2b keep: audit dot error/denied=danger, blocked=warning, else harmless=success. */}
                  <span
                    data-testid="audit-entry-state"
                    title={
                      e.decision === 'blocked'
                        ? t('agentPanel.auditBlocked')
                        : e.status === 'error' || e.decision === 'denied'
                          ? t('agentPanel.auditDenied')
                          : undefined
                    }
                    className={`mt-1 h-1.5 w-1.5 rounded-full shrink-0 ${
                      e.status === 'error' || e.decision === 'denied'
                        ? 'bg-status-danger'
                        : e.decision === 'blocked' ||
                            e.decision === 'session-approved' ||
                            e.status === 'sandboxed'
                          ? 'bg-status-warning'
                          : 'bg-status-success/70'
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        data-testid="audit-entry-time"
                        className="text-ui-2xs text-ink-faint font-mono shrink-0"
                      >
                        {auditClock(e.ts)}
                      </span>
                      {/* The kind is its own piece: hook, turn and tool_exec used to
                          share one word — namely the tool name. */}
                      <span
                        data-testid="audit-entry-kind"
                        title={e.kind}
                        className="shrink-0 rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ui-2xs text-ink-faint"
                      >
                        {auditKindName(e.kind, t)}
                      </span>
                      {e.tool && (
                        <span className="text-foreground/80 font-medium truncate">{e.tool}</span>
                      )}
                      <span className="text-ui-2xs text-ink-faint font-mono">
                        {e.decision || e.status}
                      </span>
                      <span className="flex-1" />
                      {auditDuration(e.duration_ms, lang) && (
                        <span
                          data-testid="audit-entry-duration"
                          title={t('agentPanel.auditDuration')}
                          className="text-ui-2xs text-ink-faint font-mono shrink-0"
                        >
                          {auditDuration(e.duration_ms, lang)}
                        </span>
                      )}
                    </div>
                    {(e.args || e.args_hash) && (
                      <div className="flex items-baseline gap-2 min-w-0">
                        {e.args && (
                          <p className="text-ink-faint truncate font-mono text-ui-xs min-w-0">
                            {e.args}
                          </p>
                        )}
                        {auditSignature(e.args_hash) && (
                          <span
                            data-testid="audit-entry-signature"
                            title={`${t('agentPanel.auditArgsHash')}: ${e.args_hash}`}
                            className="text-ui-2xs text-ink-faint font-mono shrink-0"
                          >
                            {auditSignature(e.args_hash)}
                          </span>
                        )}
                      </div>
                    )}
                    {/* detail sits on every row (mode, tool count, reason) —
                        it used to be limited to error rows. */}
                    {e.detail && (
                      <p
                        data-testid="audit-entry-detail"
                        title={e.detail}
                        className={`truncate ${
                          e.status === 'error' ? 'text-status-danger/80' : 'text-ink-faint'
                        }`}
                      >
                        {e.detail}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
