/**
 * The companion in the active chat: the bee (or the spark) that outlives the
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
import { useReducedMotion } from 'framer-motion'
import { useDeepBool, useDeepNumber, useDeepSelect } from '@/lib/deepSettings'
import type { RunState } from './AgenticBar'
import { CompanionQuickPanel } from './CompanionQuickPanel'
import type { CompanionSpecies } from './CompanionActor'
import { companionMood } from './companionState'
import { useCompanionCopilot } from '@/lib/useCompanionCopilot'
import { useSetupRepair } from '@/lib/companionRepair'
import type { CopilotMode } from '@/lib/companionCopilot'
import { useTranslation } from 'react-i18next'

const SPECIES: CompanionSpecies[] = ['fire_bee', 'ember_spark', 'minimal']

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
  const species = useDeepSelect('appearance.companion_species', 'fire_bee')
  const behavior = useDeepSelect('appearance.companion_behavior', 'interactive')
  const mode = useDeepSelect('appearance.companion_mode', 'copilot')
  const scale = useDeepNumber('appearance.companion_scale', 100)
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const reduced = useReducedMotion()
  const mood = companionMood(runState)
  const still = Boolean(reduced) || !animationsEnabled || mood === 'still' || mood === 'settle'
  const repairVisible = useSetupRepair()
  // The co-pilot loop runs in exactly one surface: the perch the register chose,
  // and only once the chat has something to crawl. A second instance would
  // approve the same prompt twice.
  const shows = enabled && hasMessages && behavior !== 'welcome_only' && behavior !== 'header'

  const copilot = useCompanionCopilot({
    enabled: shows,
    mode: mode as CopilotMode,
    runState,
    contextPercent: contextPercent ?? null,
    repairVisible,
  })

  if (!shows) return null

  const form = SPECIES.includes(species as CompanionSpecies)
    ? (species as CompanionSpecies)
    : 'fire_bee'
  const interact = behavior === 'interactive'
  const finding = copilot.finding
  const countingDown = copilot.countdownRemaining !== null

  return (
    <div
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
