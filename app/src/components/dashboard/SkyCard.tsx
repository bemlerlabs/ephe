/**
 * Ephe — the ephemerides as a surface (S4 → owner feedback 2026-09-28)
 *
 * TWO places, no welcome overload:
 * - SkyPanel: its own area in the settings hub (tab „Ephemeriden") — orbits
 *   AND token usage per day (bars). The token sums are produced LOCALLY from
 *   the session store with the same estimation formula as the context meter
 *   (4.2 characters/token) — no second truth.
 * - SkyStatusLine: one line inside the expandable agent status.
 *
 * Privacy through physics: the backend catalogue knows only d/h/k/n —
 * WHEN Ephe had encounters, never WHAT. Fail-soft everywhere: without a
 * backend the surface stays honestly empty instead of inventing numbers.
 */
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { getSky, type SkyData, type SkyDayRow } from '@/lib/api'
import { useChatStore } from '@/store/chatStore'
import { estimateTokens } from '@/lib/contextMeter'
import { fmtTokensCompact } from '@/lib/format'
import type { Session } from '@/types'

/** One day column: 24 hour cells, peak bright, active hours dimmed. */
export function SkyHourGrid({ row }: { row: SkyDayRow }) {
  const peak = row.peak_hour
  const cells = []
  for (let h = 0; h < 24; h++) {
    const n = row.hours[String(h)] ?? 0
    cells.push(
      <span
        key={h}
        title={`${row.weekday} ${row.label} · ${String(h).padStart(2, '0')}:00 · ${n}`}
        className={`h-[6px] rounded-[1px] ${h === peak ? 'bg-brand' : n > 0 ? 'bg-brand/40' : 'bg-surface-raised'}`}
      />,
    )
  }
  return (
    <div
      className="flex-1 grid"
      style={{ gridTemplateColumns: 'repeat(24, minmax(0, 1fr))', gap: '2px' }}
      role="img"
    >
      {cells}
    </div>
  )
}

/** Token sums per calendar day (YYYY-MM-DD, local time) from the local session
 * store — the same estimation formula as the context meter. Purely read-only. */
export function computeTokensByDay(sessions: Session[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const s of sessions ?? []) {
    for (const m of s.messages ?? []) {
      const d = new Date(m.timestamp)
      if (Number.isNaN(d.getTime())) continue
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      const streamed = (m.content ?? '') + (m.thinking?.text ?? '')
      out[key] = (out[key] ?? 0) + estimateTokens(streamed)
    }
  }
  return out
}

/**
 * The ephemerides area (settings tab): overview + 7 day rows with an hour
 * grid, orbit count and token bar (relative to the strongest day).
 */
export function SkyPanel() {
  const { t, i18n } = useTranslation()
  const [sky, setSky] = useState<SkyData | null>(null)
  const [failed, setFailed] = useState(false)
  const sessions = useChatStore((st) => st.sessions)
  const tokensByDay = useMemo(() => computeTokensByDay(sessions), [sessions])

  useEffect(() => {
    let cancelled = false
    getSky(7)
      .then((s) => {
        if (!cancelled) setSky(s)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (failed) {
    return <p className="text-ui-xs text-ink-faint">{t('settings.healthFail')}</p>
  }
  if (!sky) {
    return (
      <div className="flex items-center justify-center h-24">
        <Loader2 className="h-4 w-4 animate-spin text-brand/50" />
      </div>
    )
  }
  if (!sky.available) {
    return <p className="text-ui-xs text-ink-faint">{t('settings.healthFail')}</p>
  }

  const weekTokens = Object.values(tokensByDay).reduce((a, b) => a + b, 0)
  const activeDays = sky.rows.filter((r) => r.total > 0).length
  const maxDayTokens = Math.max(1, ...sky.rows.map((r) => tokensByDay[r.d] ?? 0))

  return (
    <div className="space-y-3" data-testid="sky-panel">
      <div className="glass-reading rounded-xl p-4 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-ui-xs uppercase tracking-wider text-ink-faint">
            {t('sky.total', { count: sky.total })}
          </span>
          <span className="text-ui-xs font-mono tabular-nums text-ink-soft">
            {fmtTokensCompact(weekTokens, i18n.language)} tok
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-ui-xs text-ink-faint">
            {t('sky.activeDays', { count: activeDays })} ·{' '}
            {t('sky.sessions', { count: sky.kinds.session })}
          </span>
          {sky.faded > 0 && (
            <span className="text-ui-xs font-mono text-ink-faint">
              {t('sky.faded', { count: sky.faded })}
            </span>
          )}
        </div>
      </div>

      <div data-testid="sky-chart" className="glass-reading rounded-xl p-3 flex flex-col gap-2.5">
        {sky.rows.map((row) => {
          const dayTokens = tokensByDay[row.d] ?? 0
          return (
            <div key={row.d} className="flex flex-col gap-1" data-testid={`sky-day-${row.d}`}>
              <div className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-ui-xs font-mono text-ink-faint">
                  {row.weekday} {row.label}
                </span>
                <SkyHourGrid row={row} />
              </div>
              <div className="flex items-center gap-2 pl-16">
                <div className="flex-1 h-1.5 rounded-full bg-surface-raised overflow-hidden">
                  <div
                    className="h-full rounded-full bg-brand/70 transition-all"
                    style={{
                      width: `${Math.max((dayTokens / maxDayTokens) * 100, dayTokens > 0 ? 2 : 0)}%`,
                    }}
                  />
                </div>
                <span className="w-24 shrink-0 text-right text-ui-xs font-mono tabular-nums text-ink-faint">
                  {fmtTokensCompact(dayTokens, i18n.language)} tok
                </span>
                <span className="w-16 shrink-0 text-right text-ui-xs font-mono tabular-nums text-ink-faint">
                  {t('sky.bahnen', { count: row.total })}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-ui-xs text-ink-faint leading-relaxed">{t('sky.privacy')}</p>
    </div>
  )
}

/** Line in the expandable status (S4): today N · week M orbits. Fail-soft —
 * without a backend the line stays hidden, it never lies. */
export function SkyStatusLine() {
  const { t } = useTranslation()
  const [sky, setSky] = useState<SkyData | null>(null)

  useEffect(() => {
    let cancelled = false
    getSky(7)
      .then((s) => {
        if (!cancelled) setSky(s)
      })
      .catch(() => {
        /* offline → the line stays hidden */
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!sky || !sky.available) return null
  const today = sky.today ? (sky.rows.find((r) => r.d === sky.today)?.total ?? 0) : 0
  return (
    <p
      data-testid="sky-status-line"
      className="text-ui-xs font-mono tabular-nums text-ink-faint px-0.5 py-1"
      title={t('sky.chartHint')}
    >
      ◑ {t('sky.statusLine', { today, week: sky.total })}
    </p>
  )
}
