'use client'

/**
 * The run rail: the steps of the current run down the edge of the work column, one
 * mark each, toned by the step's own status — the persistent companion to the plan
 * card that scrolls away with its message. It reads the plan the newest turn already
 * carries and produces nothing of its own; the still mark is the accent when a step
 * is live (`globals.css`, `.ephe-rail-mark`).
 */
import { useTranslation } from 'react-i18next'
import type { PlanCardSpec } from '@/types'

export default function RunRail({ plan }: { plan?: PlanCardSpec | null }) {
  const { t } = useTranslation()
  if (!plan || plan.total === 0) return null
  const label = t('workbench.runProgress', { done: plan.done, total: plan.total })
  return (
    <div
      data-testid="run-rail"
      role="img"
      aria-label={label}
      title={label}
      className="hidden w-6 flex-shrink-0 select-none flex-col items-center gap-1.5 self-stretch py-3 lg:flex"
    >
      {plan.items.map((step, i) => (
        <span
          key={i}
          data-testid={`run-rail-step-${i}`}
          data-step={step.status}
          className="ephe-rail-mark h-1.5 w-1.5"
          title={step.text}
        />
      ))}
    </div>
  )
}
