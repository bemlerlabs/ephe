'use client'

import { ShieldCheck } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import type { MarketPermissionDelta, MarketPlugin, MarketVersion } from '@/lib/api'
import type { SettingsModel } from '../types'

type T = SettingsModel['t']

export interface PendingInstall {
  sourceId: string
  plugin: MarketPlugin
  version: MarketVersion
  unsigned: boolean
  delta?: MarketPermissionDelta
}

const BUTTON =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg px-2.5 py-1 text-ui-xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink disabled:opacity-40 pointer-coarse:min-h-11'
const PRIMARY =
  'focus-ring inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg bg-brand/90 px-3 py-1.5 text-ui-xs font-medium text-white transition-colors hover:bg-brand disabled:opacity-40 pointer-coarse:min-h-11'

export function MarketReview({
  pending,
  t,
  onApprove,
  onCancel,
}: {
  pending: PendingInstall
  t: T
  onApprove: () => void
  onCancel: () => void
}) {
  return (
    <SettingsGroup
      icon={ShieldCheck}
      title={pending.delta ? t('settings.marketPermissionReview') : t('settings.marketTrustReview')}
      testid="market-review"
    >
      <div className="space-y-2 px-4 py-3">
        <p className="text-ui-xs text-ink-soft">
          {pending.plugin.displayName} → v{pending.version.version}
        </p>
        {pending.unsigned && (
          <p className="text-ui-2xs text-status-warning">{t('settings.marketUnsignedHint')}</p>
        )}
        {pending.delta && (
          <div className="space-y-1 text-ui-2xs text-ink-soft">
            <p>
              {t('settings.marketPermissions')}: +
              {pending.delta.tool_families_added.join(', ') || '—'}
            </p>
            <p>
              {t('settings.marketComponents')}: {pending.version.components.join(', ') || '—'}
            </p>
          </div>
        )}
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={PRIMARY}
            onClick={onApprove}
            data-testid="market-approve"
          >
            {t('settings.marketApproveInstall')}
          </button>
          <button type="button" className={BUTTON} onClick={onCancel}>
            {t('settings.marketCancel')}
          </button>
        </div>
      </div>
    </SettingsGroup>
  )
}
