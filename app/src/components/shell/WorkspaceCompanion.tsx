/**
 * The companion in the active chat: the moth (or the spark) that outlives the
 * onboarding. It sits above the composer, moves toward the answer while the
 * engine works, and opens its quick panel on click.
 *
 * QD-005: this is also where the co-pilot lives. One crawl per surface change
 * (`useCompanionCopilot`), a visible 2.5 s countdown before any automatic act,
 * and the receipts the panel shows. The run state is the one `runStateOf` hands
 * the run bar — no second health read and no private interval. `header` is the
 * header perch's place; this surface stays out of it.
 */
import './Companion.css'
import { useRef } from 'react'
import { useReducedMotion } from 'framer-motion'
import { useDeepBool, useDeepNumber, useDeepSelect } from '@/lib/deepSettings'
import type { RunState } from './AgenticBar'
import { CompanionQuickPanel } from './CompanionQuickPanel'
import type { CompanionSpecies } from './CompanionActor'
import { companionMood } from './companionState'
import { useCompanionCopilot } from '@/lib/useCompanionCopilot'
import { useSetupRepair } from '@/lib/companionRepair'
import { useCompanionDrag } from './useCompanionDrag'
import type { CopilotMode } from '@/lib/companionCopilot'
import { useTranslation } from 'react-i18next'

const SPECIES: CompanionSpecies[] = ['paper_moth', 'fire_bee', 'ember_spark', 'minimal']

export default function WorkspaceCompanion({
  runState,
  hasMessages,
  contextPercent,
}: {
  runState: RunState
  hasMessages: boolean
  contextPercent?: number | null
}) {
  const { t } = useTranslation()
  const enabled = useDeepBool('appearance.companion_enabled', false)
  const species = useDeepSelect('appearance.companion_species', 'paper_moth')
  const behavior = useDeepSelect('appearance.companion_behavior', 'interactive')
  const mode = useDeepSelect('appearance.companion_mode', 'copilot')
  const scale = useDeepNumber('appearance.companion_scale', 100)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const reduced = useReducedMotion()
  const mood = companionMood(runState)
  const still = Boolean(reduced) || !animationsEnabled || mood === 'still' || mood === 'settle'
  const repairVisible = useSetupRepair()
  const box = useRef<HTMLDivElement>(null)
  // Only the figure itself starts a drag: the copilot chip and the open panel
  // carry their own controls, and a press on one of them is a press on it.
  const pet = useCompanionDrag(
    box,
    (target) => target instanceof Element && target.closest('[data-testid="companion-trigger"]') !== null,
  )
  // The co-pilot loop runs in exactly one surface: the perch the register chose.
  // A second instance would approve the same prompt twice. The creature itself
  // is also on the welcome screen — the header switch refused to show anything
  // there, so clicking it looked broken (QA-0.1.11, R1) — and `welcome_only`
  // now means what its label says instead of hiding the figure everywhere.
  const onWelcome = !hasMessages
  const shows =
    enabled &&
    behavior !== 'header' &&
    (behavior === 'welcome_only' ? onWelcome : true)

  const copilot = useCompanionCopilot({
    // The crawl needs a turn to read; on the welcome screen only the figure shows.
    enabled: shows && hasMessages,
    mode: mode as CopilotMode,
    runState,
    contextPercent: contextPercent ?? null,
    repairVisible,
  })

  if (!shows) return null

  const form = SPECIES.includes(species as CompanionSpecies)
    ? (species as CompanionSpecies)
    : 'paper_moth'
  const interact = behavior === 'interactive'
  const finding = copilot.finding
  const countingDown = copilot.countdownRemaining !== null

  return (
    <div
      ref={box}
      style={pet.style}
      {...pet.handlers}
      data-dragging={pet.dragging ? 'true' : undefined}
      data-testid="workspace-companion"
      data-behavior={behavior}
      data-species={form}
      data-state={runState}
      data-mood={mood}
      data-copilot-mode={mode}
      className={`workspace-companion is-${interact ? 'interactive' : 'perch'}${
        mood === 'moving' ? ' is-streaming' : ''
      }${mood === 'still' ? ' is-quiet' : ''}${mood === 'settle' ? ' is-settle' : ''}`}
    >
      {finding && (
        <div
          data-testid="companion-copilot-chip"
          data-verdict={finding.verdict}
          className={[
            'companion-copilot-chip',
            'glass-control',
            finding.verdict === 'focus'
              ? 'border-brand/30 text-brand'
              : 'border-status-warning/40 text-status-warning',
          ].join(' ')}
          role={countingDown ? 'timer' : 'status'}
        >
          {countingDown ? (
            <>
              <span data-testid="companion-countdown">
                {t('copilot.countdown', {
                  seconds: Math.ceil((copilot.countdownRemaining ?? 0) / 1000),
                })}
              </span>
              <button
                type="button"
                data-testid="companion-countdown-cancel"
                aria-label={t('copilot.cancel')}
                onClick={copilot.cancel}
                className="focus-ring rounded-md border border-status-warning/40 px-2 py-0.5 text-ui-xs text-status-warning hover:bg-status-warning/10"
              >
                {t('copilot.cancel')}
              </button>
            </>
          ) : finding.verdict === 'warn_only' ? (
            <span data-testid="companion-warning">{t('copilot.warn')}</span>
          ) : (
            <>
              <span>{t(finding.actionKey, { param: finding.actionParam ?? '' })}</span>
              <button
                type="button"
                data-testid="companion-copilot-focus"
                onClick={copilot.focus}
                className="focus-ring rounded-md border border-brand/30 bg-brand/10 px-2 py-0.5 text-ui-xs text-brand hover:bg-brand/20"
              >
                {t('copilot.focus')}
              </button>
            </>
          )}
        </div>
      )}
      <CompanionQuickPanel
        runState={runState}
        species={form}
        scale={scale}
        still={still}
        placement="composer"
        mode={mode as CopilotMode}
        receipts={copilot.receipts}
        finding={finding}
        countdownRemaining={copilot.countdownRemaining}
        onCancelCountdown={copilot.cancel}
        onFocus={copilot.focus}
      />
    </div>
  )
}
