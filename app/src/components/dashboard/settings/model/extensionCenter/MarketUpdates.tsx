'use client'

import { Loader2, ShieldCheck } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import type { MarketUpdate } from '@/lib/api'
import type { SettingsModel } from '../types'

type T = SettingsModel['t']

const PRIMARY =
  'focus-ring inline-flex min-h-8 items-center justify-center gap-1.5 rounded-lg bg-brand/90 px-3 py-1 text-ui-xs font-medium text-white transition-colors hover:bg-brand disabled:opacity-40 pointer-coarse:min-h-11'

export function MarketUpdates({
  updates,
  errors,
  busy,
  t,
  onUpdate,
}: {
  updates: MarketUpdate[]
  errors: { source: string; error: string }[]
  busy: string
  t: T
  onUpdate: (update: MarketUpdate) => void
}) {
  return (
    <SettingsGroup
      icon={ShieldCheck}
      title={t('settings.marketUpdates')}
      testid="market-update-list"
    >
      <div className="space-y-2 px-4 py-3">
        {errors.map((error) => (
          <p key={error.source} className="text-ui-2xs text-status-warning">
            {error.source}: {error.error}
          </p>
        ))}
        {updates.length === 0 ? (
          <p className="text-ui-xs text-ink-faint">{t('settings.marketNoUpdates')}</p>
        ) : (
          updates.map((update) => (
            <div
              key={`${update.source_id}:${update.name}`}
              data-testid={`market-update-row-${update.name}`}
              className="flex flex-wrap items-center gap-2 rounded-lg bg-surface/50 px-2.5 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-ui-xs text-ink">
                {update.name}{' '}
                <span className="font-mono text-ui-2xs text-ink-faint">
                  {update.installed_version} → {update.version}
                </span>
              </span>
              <span className="text-ui-2xs text-ink-faint">{update.source_title}</span>
              <button
                type="button"
                className={PRIMARY}
                onClick={() => onUpdate(update)}
                disabled={Boolean(busy)}
              >
                {busy === update.name ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                {t('settings.marketUpdate')}
              </button>
            </div>
          ))
        )}
      </div>
    </SettingsGroup>
  )
}
