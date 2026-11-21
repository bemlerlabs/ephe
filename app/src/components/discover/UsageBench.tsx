/**
 * The bench — what this machine's own audit log measured. Every bar is a call
 * count from `GET /api/audit/usage`, so the strip is a readout of the last turns
 * and grows as the user works. It carries no number this route did not send.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity } from 'lucide-react'
import type { ToolUsageRow, ToolUsageView } from '@/lib/api'
import { toolLabel } from './toolLabel'

const MAX_ROWS = 6

function Bar({
  row,
  max,
  armed,
  capped,
}: {
  row: ToolUsageRow
  max: number
  armed: boolean
  capped: boolean
}) {
  const { t } = useTranslation()
  const pct = max > 0 ? Math.max(4, Math.round((row.calls / max) * 100)) : 0
  const share = row.calls > 0 ? Math.round((row.ok / row.calls) * 100) : 0
  return (
    <li
      data-testid={`discover-bench-row-${row.tool}`}
      className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 ${capped ? 'max-sm:hidden' : ''}`}
      title={row.blocked > 0 ? t('discover.benchBlocked', { count: row.blocked }) : undefined}
    >
      <span className="truncate text-ui-xs text-ink-soft">{toolLabel(row.tool)}</span>
      <span className="font-mono text-ui-xs tabular-nums text-foreground/90">{row.calls}</span>
      <span aria-hidden="true" className="h-1 overflow-hidden rounded-full bg-hairline/50">
        <span
          className={`block h-full rounded-full transition-[width] duration-slow ease-out-soft motion-reduce:transition-none ${
            row.errors > 0 ? 'bg-status-warning/80' : 'bg-brand/75'
          }`}
          style={{ width: armed ? `${pct}%` : '0%' }}
        />
      </span>
      <span
        className={`font-mono text-ui-2xs tabular-nums ${
          row.errors > 0 ? 'text-status-warning' : 'text-ink-faint'
        }`}
      >
        {t('discover.benchShare', { share })}
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
      className="flex flex-col rounded-2xl border border-hairline bg-surface/55 p-4"
      aria-labelledby="discover-bench-title"
    >
      <header className="mb-4 flex items-start gap-2.5">
        <span
          aria-hidden="true"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-surface-raised/60 text-ink-faint"
        >
          <Activity className="h-3.5 w-3.5" strokeWidth={1.5} />
        </span>
        <div className="min-w-0">
          <h2 id="discover-bench-title" className="text-ui-sm font-semibold text-foreground/95">
            {t('discover.benchTitle')}
          </h2>
          <p className="mt-0.5 text-ui-2xs leading-relaxed text-ink-faint">
            {view ? t('discover.benchLede', { window: view.window }) : t('discover.benchLoading')}
          </p>
        </div>
      </header>

      {rows.length === 0 ? (
        <p data-testid="discover-bench-empty" className="text-ui-xs leading-relaxed text-ink-soft">
          {view ? t('discover.benchNone') : t('discover.benchLoading')}
        </p>
      ) : (
        <ul className="grid gap-3">
          {rows.map((row, index) => (
            // A phone shows the first three calls; the desk shows all six.
            <Bar key={row.tool} row={row} max={max} armed={armed} capped={index >= 3} />
          ))}
        </ul>
      )}

      {view && rows.length ? (
        <p
          data-testid="discover-bench-reach"
          className="mt-auto border-t border-hairline pt-3 text-ui-2xs tabular-nums text-ink-faint"
        >
          {t('discover.benchReach', { population: view.population, window: view.window })}
        </p>
      ) : null}
    </section>
  )
}
