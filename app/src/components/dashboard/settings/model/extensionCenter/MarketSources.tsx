'use client'

import { Globe, ShieldCheck } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import type { MarketHome } from '@/lib/api'
import type { SettingsModel } from '../types'

type T = SettingsModel['t']

/**
 * The catalog is curated. There is deliberately no add, remove or refresh
 * control here: a user cannot introduce a source or a plugin, and the only
 * catalog the surface reads is the bundled one. Owner-provisioned enterprise
 * sources are a backend decision, not a settings action.
 */
export function MarketSources({
  home,
  digest,
  t,
}: {
  home: MarketHome | null
  digest?: string
  t: T
}) {
  const source = (home?.sources ?? []).find((item) => item.id === 'bundled') ?? home?.sources?.[0]
  const read = source ? home?.last_read?.[source.id] : ''
  const error = source ? home?.last_error?.[source.id] : ''

  return (
    <SettingsGroup icon={Globe} title={t('settings.marketCatalog')} testid="market-sources">
      <div className="space-y-1.5 px-4 py-3" data-testid="market-catalog">
        <p className="text-ui-xs text-ink-soft">{t('settings.marketCatalogCurated')}</p>
        {source && (
          <p className="font-mono text-ui-xs tabular-nums text-ink-faint">
            {source.title} · {t('settings.marketSourceBundled')}
            {read ? ` · ${t('settings.marketSourceLastRead')}: ${read}` : ''}
          </p>
        )}
        {digest && (
          <p
            className="flex items-center gap-1.5 font-mono text-ui-xs tabular-nums text-ink-faint"
            data-testid="market-catalog-seal"
            title={digest}
          >
            <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-status-success" strokeWidth={1.5} />
            {t('settings.marketCatalogSeal')}: {digest.slice(0, 16)}…
          </p>
        )}
        {error && (
          <p className="text-ui-xs text-status-danger">
            {t('settings.marketSourceError')}: {error}
          </p>
        )}
      </div>
    </SettingsGroup>
  )
}
