'use client'

import type { AgentRecord } from '@/lib/api'
import type { SettingsModel } from './types'

export type T = SettingsModel['t']

export const FIELD =
  'w-full rounded-lg border border-control bg-background/60 px-2.5 py-2 text-ui-sm text-foreground/90 placeholder:text-ink-faint focus-ring focus:border-brand/50 focus:outline-none pointer-coarse:min-h-11'
export const BUTTON =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg px-2.5 py-1 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink disabled:opacity-40 pointer-coarse:min-h-11'
export const PRIMARY =
  'focus-ring inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg bg-brand/90 px-3 py-1.5 text-ui-xs font-medium text-white transition-colors hover:bg-brand disabled:opacity-40 pointer-coarse:min-h-11'

export const DEFAULT_TOOLS = ['read_file', 'list_directory', 'file_search', 'web_search']

export function originLabel(origin: string, t: T): string {
  if (origin === 'ephe') return t('settings.agentOriginEphe')
  if (origin.startsWith('plugin:')) return `${t('settings.agentOriginPlugin')} · ${origin.slice(7)}`
  return t('settings.agentOriginLocal')
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

export function agentAvatar(name: string): string {
  const tones = [
    'from-brand/70 to-brand-deep/60',
    'from-status-success/60 to-brand/50',
    'from-status-warning/60 to-brand-deep/50',
    'from-brand-deep/60 to-ink/40',
  ]
  let sum = 0
  for (const char of name) sum += char.charCodeAt(0)
  return tones[sum % tones.length] ?? 'from-brand/70 to-brand-deep/60'
}

export function blankAgent(): Partial<AgentRecord> {
  return {
    name: '',
    description: '',
    instructions: '',
    model: null,
    tools: [...DEFAULT_TOOLS],
    permissions: { approval: 'inherit', rules: [] },
    limits: { max_turns: 8, timeout: 180 },
    enabled: true,
    archived: false,
  }
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
