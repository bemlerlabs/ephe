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
import { PaperMothGlyph } from '@/components/brand/PaperMothGlyph'
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
  onOpenPalette,
  inline = false,
}: {
  state: RunState
  plan?: PlanCardSpec | null
  onOpenPalette: () => void
  /** B1: rendered inside the chat header instead of as a row of its own. */
  inline?: boolean
}) {
  const { t } = useTranslation()
  const progress = plan && plan.total > 0 ? plan.done / plan.total : null
  return (
    <div
      data-testid="agentic-bar"
      data-state={state}
      className={
        inline
          ? 'ephe-run relative flex h-full min-w-0 flex-1 items-center gap-2 overflow-hidden select-none max-sm:min-w-11'
          : 'workbench-bar ephe-run relative flex h-8 flex-shrink-0 items-center gap-3 px-4 max-lg:h-10 select-none'
      }
    >
      <span
        data-testid="workbench-state"
        className="inline-flex shrink-0 items-center gap-1.5 text-ui-xs text-ink-soft"
      >
        <PaperMothGlyph
          size="18px"
          className="ephe-run-mark max-[379px]:hidden"
          testId="agentic-moth"
        />
        {/* Below 430 px the run line and the palette button cannot both stand in
            the header's last pixels; the word keeps its place in the live region,
            the mark alone states the run, and under 380 px the bar belongs to the
            palette button so the state moves entirely behind the screen reader. */}
        <span className="max-[429px]:sr-only">{t(`workbench.${state}`)}</span>
      </span>
      {plan && plan.total > 0 && (
        <span
          data-testid="workbench-plan"
          className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint max-sm:hidden"
        >
          {t('workbench.steps', { done: plan.done, total: plan.total })}
        </span>
      )}
      <button
        type="button"
        onClick={onOpenPalette}
        aria-label={`${t('chat.openPalette')} (⌘K)`}
        title={`${t('chat.openPalette')} (⌘K)`}
        data-testid="workbench-command"
        className="focus-ring ml-auto inline-flex shrink-0 items-center justify-center gap-1 rounded-md px-1.5 py-0.5 min-h-6 min-w-6 text-ui-2xs text-ink-faint transition-colors hover:bg-surface-interactive hover:text-foreground pointer-coarse:min-h-11 pointer-coarse:min-w-11"
      >
        <Command className="h-3 w-3" aria-hidden="true" />
        {/* The chord stays in the name, not as a second glyph beside the icon:
            the inline bar already sits next to the composer's own palette button. */}
        {inline ? null : <span className="tabular-nums">&#8984;K</span>}
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
