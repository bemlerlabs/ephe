import { useEffect } from 'react'
import { formatPercent } from '@/lib/contextMeter'
import type { ContextBudget } from '@/lib/api'
import { formatNumber, formatRate } from '@/lib/dateLocale'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { windowHint } from './windowHint'

/**
 * R43 (reference parity): compact "Context windows" pop-up — full/window value
 * with percent, progress bar and category shares from the backend breakdown.
 * Portaled to the body (clip-immune, like the artifact modal); the token pill is
 * the only opener, Esc closes.
 */
export function ContextWindowsPopover({
  budget,
  tokens,
  window,
  percent,
  compactionActive,
  tokPerSec,
  ttftMs,
}: {
  budget: ContextBudget | null
  /** W3-52: the effective figures the row shows — passed in, not re-derived from
   *  `budget`. The row applies a mirror-live gate and a `windowTokens` fallback;
   *  reading `budget.estimated_tokens`/`budget.window_tokens` here printed a second
   *  pair for the same session whenever the mirror was empty or only the prop
   *  carried the window. */
  tokens: number
  window: number
  percent: number
  compactionActive: boolean
  /** W19 F5: secondary metrics of the running turn — now inside the popover. */
  tokPerSec: number | null
  ttftMs: number | null
}) {
  const { t, i18n } = useTranslation()
  const rows = budget?.breakdown ?? []
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        const el = document.querySelector('[data-testid="statusbar-tok-chip"]')
        if (el instanceof HTMLElement) el.click()
      }
    }
    globalThis.addEventListener('keydown', onKey)
    return () => globalThis.removeEventListener('keydown', onKey)
  }, [])
  return createPortal(
    <div
      role="dialog"
      aria-label={t('statusBar.contextWindowTitle')}
      data-testid="context-popover"
      className="fixed left-1/2 top-[64px] -translate-x-1/2 z-modal w-[min(560px,92vw)] float-surface bg-canvas px-3 py-2.5"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-ui-sm font-medium text-foreground">
          {t('statusBar.contextWindowTitle')}
        </span>
        <span className="text-ui-xs font-mono tabular-nums text-ink-faint">
          {formatNumber(tokens, i18n.language)} / {formatNumber(window, i18n.language)} (
          {formatPercent(Math.min(percent, 100), i18n.language)})
        </span>
      </div>
      {/* Track with its own visibility floor, so the bar still reads as one
          continuous track at 0%; the filling segment carries the colour. */}
      <div className="mt-1.5 h-1 w-full rounded-full bg-surface-raised overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.max(Math.min(percent, 100), 1.5)}%`,
            background:
              percent >= 95
                ? 'rgb(248 113 113)'
                : percent >= 60
                  ? 'rgb(251 191 36)'
                  : 'rgb(74 222 128)',
          }}
        />
      </div>
      {/* F2: the source sentence, said out loud. The meter keeps it as a title,
          and a title never renders on a touch screen — this popover is what the
          token pill opens on a phone. */}
      <p className="mt-1.5 text-ui-xs text-ink-faint" data-testid="statusbar-window-source">
        {windowHint(budget, window, t, i18n.language)}
      </p>
      {compactionActive && (
        <p className="mt-1.5 text-ui-xs text-status-warning/90">
          {t('statusBar.compactionActive')}
        </p>
      )}
      {/* W19 F5: live metrics of the running turn (moved here out of the row). */}
      {(tokPerSec !== null || ttftMs != null) && (
        <div className="mt-1.5 flex flex-col gap-0.5">
          {tokPerSec !== null && (
            <span
              className="text-ui-xs font-mono tabular-nums text-brand/80"
              title={t('statusBar.tokPerSecHint')}
            >
              {formatRate(tokPerSec, i18n.language)} tok/s
            </span>
          )}
          {ttftMs != null && (
            <span
              className="text-ui-xs font-mono tabular-nums text-ink-faint"
              title={t('statusBar.ttftHint')}
            >
              TTFT {formatRate(ttftMs / 1000, i18n.language)}s
            </span>
          )}
        </div>
      )}
      {rows.length > 0 && (
        <ul className="mt-1.5 flex flex-col gap-0.5">
          {rows.map((r) => (
            <li
              key={r.name}
              className="flex items-center justify-between text-ui-xs font-mono text-ink-soft"
            >
              <span>{r.name}</span>
              <span className="tabular-nums text-ink-soft">
                {formatNumber(r.percent, i18n.language, 3)}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>,
    document.body,
  )
}
