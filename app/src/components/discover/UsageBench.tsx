/**
 * The bench — what this machine's own audit log measured. Every bar is a call
 * count from `GET /api/audit/usage`, so the strip is a readout of the last turns
 * and grows as the user works. It carries no number this route did not send.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ToolUsageRow, ToolUsageView } from '@/lib/api'

const MAX_ROWS = 8

/** `417 / 500` in the head says how far back the ranking reaches. */
function Reach({ view }: { view: ToolUsageView }) {
  const { t } = useTranslation()
  return (
    <span data-testid="discover-bench-reach" className="font-mono text-ui-xs text-ink-faint">
      {t('discover.benchReach', { population: view.population, window: view.window })}
    </span>
  )
}

function Bar({ row, max, armed }: { row: ToolUsageRow; max: number; armed: boolean }) {
  const { t } = useTranslation()
  const pct = max > 0 ? Math.max(2, Math.round((row.calls / max) * 100)) : 0
  const share = row.calls > 0 ? Math.round((row.ok / row.calls) * 100) : 0
  return (
    <li
      data-testid={`discover-bench-row-${row.tool}`}
      className="group/bench grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-1"
    >
      <span className="truncate font-mono text-ui-xs text-ink-soft group-hover/bench:text-foreground">
        {row.tool}
      </span>
      <span className="text-right font-mono text-ui-xs tabular-nums text-foreground">
        {row.calls}
        <span className="ml-1 text-ink-faint">
          {t('discover.benchShare', { share })}
          {row.blocked > 0 ? ` · ${t('discover.benchBlocked', { count: row.blocked })}` : ''}
        </span>
      </span>
      <span
        aria-hidden="true"
        className="col-span-2 h-[3px] overflow-hidden rounded-full bg-hairline/50"
      >
        <span
          className={`block h-full rounded-full bg-brand/70 transition-[width] duration-slow ease-out-soft motion-reduce:transition-none ${
            row.errors > 0 ? 'bg-status-warning/70' : ''
          }`}
          style={{ width: armed ? `${pct}%` : '0%' }}
        />
      </span>
    </li>
  )
}

export function UsageBench({ view }: { view: ToolUsageView | null }) {
  const { t } = useTranslation()
  const rows = (view?.tools ?? []).slice(0, MAX_ROWS)
  const max = rows.reduce((one, row) => Math.max(one, row.calls), 0)
  const [armed, setArmed] = useState(false)

  useEffect(() => {
    setArmed(false)
    const id = requestAnimationFrame(() => setArmed(true))
    return () => cancelAnimationFrame(id)
  }, [view])

  return (
    <section
      data-testid="discover-bench"
      className="glass-float rounded-2xl border border-hairline p-4 shadow-elevation-2"
      aria-labelledby="discover-bench-title"
    >
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 id="discover-bench-title" className="text-ui-xs font-semibold uppercase tracking-wide text-ink-faint">
          {t('discover.benchTitle')}
        </h2>
        {view ? <Reach view={view} /> : null}
      </header>

      {rows.length === 0 ? (
        <p data-testid="discover-bench-empty" className="text-ui-sm text-ink-soft">
          {view ? t('discover.benchNone') : t('discover.benchLoading')}
        </p>
      ) : (
        <ul className="grid gap-3">
          {rows.map((row) => (
            <Bar key={row.tool} row={row} max={max} armed={armed} />
          ))}
        </ul>
      )}
    </section>
  )
}
