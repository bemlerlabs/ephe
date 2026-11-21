'use client'

import type { TeamRecord } from '@/lib/api'
import type { SettingsModel } from './types'

export type T = SettingsModel['t']

export const FIELD =
  'w-full rounded-lg border border-control bg-background/60 px-2.5 py-2 text-ui-sm text-foreground/90 placeholder:text-ink-faint focus-ring focus:border-brand/50 focus:outline-none pointer-coarse:min-h-11'
export const BUTTON =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg px-2.5 py-1 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink disabled:opacity-40 pointer-coarse:min-h-11'
export const PRIMARY =
  'focus-ring inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg bg-brand/90 px-3 py-1.5 text-ui-xs font-medium text-white transition-colors hover:bg-brand disabled:opacity-40 pointer-coarse:min-h-11'

export const BLANK: Partial<TeamRecord> = {
  name: '',
  description: '',
  instructions: '',
  leader_id: '',
  member_ids: [],
  orchestration: 'parallel',
  model_policy: 'inherit',
  model: null,
  budget: { max_rounds: 4, wall_timeout: 300 },
  shared_context: { session: true, workspace: true, artifacts: false, memory: true },
}

export const TEMPLATE_TEXT: Record<string, { name: string; description: string }> = {
  research: { name: 'teamTemplateResearchName', description: 'teamTemplateResearchDesc' },
  'code-review': {
    name: 'teamTemplateCodeReviewName',
    description: 'teamTemplateCodeReviewDesc',
  },
  release: { name: 'teamTemplateReleaseName', description: 'teamTemplateReleaseDesc' },
  'product-design': {
    name: 'teamTemplateProductDesignName',
    description: 'teamTemplateProductDesignDesc',
  },
  'data-analysis': {
    name: 'teamTemplateDataAnalysisName',
    description: 'teamTemplateDataAnalysisDesc',
  },
  support: { name: 'teamTemplateSupportName', description: 'teamTemplateSupportDesc' },
}

export function runId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(4))
  return `team-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-ui-xs font-medium text-ink-soft">{label}</span>
      {children}
      {hint && <span className="block text-ui-2xs leading-relaxed text-ink-faint">{hint}</span>}
    </label>
  )
}
