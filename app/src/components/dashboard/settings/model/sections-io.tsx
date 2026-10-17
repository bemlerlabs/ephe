'use client'

import { Check, Loader2, Smartphone } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import { TelegramPairingCard } from '../../TelegramPairingCard'
import { DiscordChannelCard } from '../../DiscordChannelCard'
import type { SettingsModel } from './types'

/** Memory metadata maintained by Ephe; `timestamp` gets its own age chip. */
export function renderMobile(model: SettingsModel) {
  const { loadMobileQR, mobileConnected, mobileError, mobileLoading, mobileQR, t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.mobileTitle')} subtitle={t('settings.mobileSubtitle')} />
      {/* I7-6: the code gets a group that states its purpose — before, the picture sat
              there without a sentence saying what it opens and when it is missing. */}
      <SettingsGroup
        icon={Smartphone}
        title={t('settings.mobileGroupPair')}
        description={t('settings.mobileGroupPairHint')}
        testid="mobile-group-pair"
      >
        <div className="space-y-4 p-3">
          {mobileLoading ? (
            <div className="flex flex-col items-center justify-center gap-2 h-32">
              <Loader2 className="h-5 w-5 animate-spin text-brand/50" />
              <p className="text-ui-xs text-ink-faint">{t('settings.tunnelLoading')}</p>
              {/* Computer-Use finding 2026-10-01: the spinner kept spinning while the
              server ran without --lan — the user was given no way out. */}
              <p className="text-ui-xs text-ink-faint text-center max-w-md">
                {t('settings.tunnelLanHint', {
                  defaultValue:
                    'Not starting? The server must run with LAN pairing enabled: `ephe serve --lan`.',
                })}
              </p>
            </div>
          ) : mobileError ? (
            <div className="space-y-3">
              <p className="text-ui-xs text-status-danger/80">{mobileError}</p>
              <button
                onClick={() => void loadMobileQR()}
                className="w-full glass-control rounded-xl h-10 text-ui-sm font-medium text-foreground/70 hover:text-foreground hover:bg-brand/10 transition-all"
              >
                {t('settings.reload')}
              </button>
            </div>
          ) : mobileQR ? (
            <div className="space-y-4">
              <div className="flex justify-center rounded-xl bg-white p-3 max-w-[240px] mx-auto">
                <img
                  src={`data:image/png;base64,${mobileQR.qr_base64}`}
                  alt={t('settings.mobileQrAlt')}
                  className="w-full h-auto"
                  data-testid="mobile-qr"
                />
              </div>
              <p className="text-ui-sm text-ink-soft break-all text-center font-mono">
                {mobileQR.url}
              </p>
              {mobileQR.message && (
                <p className="text-ui-sm text-status-warning/80">{mobileQR.message}</p>
              )}
              <div
                className={`rounded-xl p-3 text-ui-xs font-medium flex items-center gap-2 transition-colors ${
                  mobileConnected
                    ? 'bg-status-success/10 border border-status-success/20 text-status-success'
                    : 'bg-surface-raised border border-hairline text-ink-soft'
                }`}
                data-testid="mobile-status"
              >
                {mobileConnected ? (
                  <>
                    <Check className="h-4 w-4" />
                    {t('settings.mobileConnected')}
                  </>
                ) : (
                  <>
                    <Loader2 className="h-4 w-4" />
                    {t('settings.mobileWaiting')}
                  </>
                )}
              </div>
              <button
                onClick={() => void loadMobileQR()}
                className="w-full glass-control rounded-xl h-10 text-ui-sm font-medium text-foreground/70 hover:text-foreground hover:bg-brand/10 transition-all"
              >
                {t('settings.reload')}
              </button>
            </div>
          ) : null}
        </div>
      </SettingsGroup>

      {/* R24 Telegram channel: QR pairing + devices + revoke */}
      <TelegramPairingCard />
      {/* W3d Discord channel (the R24 pattern): status + token + runner toggle */}
      <DiscordChannelCard />
    </div>
  )
}
