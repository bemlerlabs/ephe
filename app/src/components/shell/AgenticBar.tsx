'use client'

/**
 * The command/state bar: the one line of chrome that says what the run is doing and
 * frames the work under it. It reads the signals the session already carries — the
 * streaming flag, the engine's reachability, an open ask, and the plan of the newest
 * turn — so it states a state and produces no number of its own. The state drives the
 * one mark and the accent rule at the bar's foot (`globals.css`, `.ephe-run`).
 */
import { useTranslation } from 'react-i18next'
import { Command } from 'lucide-react'
import type { PlanCardSpec } from '@/types'
import './AgenticBar.css'

export type RunState = 'ready' | 'working' | 'waiting' | 'done'

export interface RunSignals {
  /** A turn is streaming right now. */
  typing: boolean
  /** The engine's own reachability; `false` means the run cannot move. */
  engineOnline?: boolean | null
  /** The active turn is paused on an unanswered ask (status 'waiting'). */
  askWaiting?: boolean
  /** The plan of the newest turn, when there is one. */
  plan?: PlanCardSpec | null
}

/** The state the workbench is in, read off `RunSignals`. A dead engine or an
 *  unanswered ask outranks streaming: the run is stopped on something. */
export function runStateOf({ typing, engineOnline, askWaiting, plan }: RunSignals): RunState {
  if (engineOnline === false || askWaiting) return 'waiting'
  if (typing) return 'working'
  if (plan && plan.total > 0 && plan.done >= plan.total) return 'done'
  return 'ready'
}

export default function AgenticBar({
  state,
  plan,
  goal,
  onOpenPalette,
}: {
  state: RunState
  plan?: PlanCardSpec | null
  goal?: string | null
  onOpenPalette: () => void
}) {
  const { t } = useTranslation()
  const progress = plan && plan.total > 0 ? plan.done / plan.total : null
  return (
    <div
      data-testid="agentic-bar"
      data-state={state}
      className="workbench-bar ephe-run relative flex h-8 flex-shrink-0 items-center gap-3 px-4 max-lg:h-10 select-none"
    >
      <span
        data-testid="workbench-state"
        className="inline-flex shrink-0 items-center gap-1.5 text-ui-xs text-ink-soft"
      >
        <span className="ephe-run-mark h-1.5 w-1.5 rounded-full" aria-hidden="true" />
        {t(`workbench.${state}`)}
      </span>
      {goal && (
        <span
          data-testid="workbench-goal"
          className="min-w-0 flex-1 truncate text-ui-xs text-ink-faint"
          title={goal}
        >
          {goal}
        </span>
      )}
      {plan && plan.total > 0 && (
        <span
          data-testid="workbench-plan"
          className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint"
        >
          {t('workbench.steps', { done: plan.done, total: plan.total })}
        </span>
      )}
      <button
        type="button"
        onClick={onOpenPalette}
        aria-label={t('chat.openPalette')}
        title={t('chat.openPalette')}
        data-testid="workbench-command"
        className="focus-ring ml-auto inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-ui-2xs text-ink-faint transition-colors hover:bg-surface-interactive hover:text-foreground"
      >
        <Command className="h-3 w-3" aria-hidden="true" />
        <span className="tabular-nums">&#8984;K</span>
      </button>
      {progress !== null && (
        <span
          data-testid="workbench-progress"
          className="ephe-run-progress absolute inset-x-0 bottom-0"
          style={{ transform: `scaleX(${progress})` }}
          aria-hidden="true"
        />
      )}
    </div>
  )
}
