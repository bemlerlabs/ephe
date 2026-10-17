'use client'

/**
 * I6-6: the Network area — the server's actual state.
 *
 * Before, there was no answer to "where is Ephe attached right now?". Bind and port
 * live only in the process environment (`run_server.py` sets them after the
 * socket choice), the LAN token is created anew per start and never persisted.
 * `GET /api/network/status` reads exactly these sources; the row shows what the
 * server does, not what the documentation promises.
 *
 * No dials, and that is justified: bind is a start-up decision
 * (`ephe start --lan`, fail-closed without an engine), CORS is built when the app is
 * imported, the token is new on every start. A switch without a reader would be the first
 * dead button in this area — so the rows name where the value is set.
 */
import { Eye, FileKey2, Globe, Lock, Network, Router, Share2 } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import type { SettingsModel } from './types'

export function NetworkSection({ model }: { model: SettingsModel }) {
  const { networkStatus, t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.networkTitle')} subtitle={t('settings.networkHint')} />

      {!networkStatus ? (
        <LoadingRow label={t('settings.networkLoading')} data-testid="network-loading" />
      ) : (
        <div className="space-y-4" data-testid="network-status">
          <SettingsGroup icon={Router} title={t('settings.networkGroupServer')}>
            <SettingsRow
              icon={Network}
              title={t('settings.networkBind')}
              description={t('settings.networkBindHint')}
              testid="network-bind"
            >
              <span className="font-mono text-ui-xs text-foreground/80">
                {networkStatus.bind_host || '—'}
                {networkStatus.bind_port ? `:${networkStatus.bind_port}` : ''}
              </span>
            </SettingsRow>
            <SettingsRow
              icon={networkStatus.lan ? Globe : Lock}
              title={t('settings.networkReach')}
              description={t(
                networkStatus.lan ? 'settings.networkReachLan' : 'settings.networkReachLocal',
              )}
              testid="network-reach"
            />
            <SettingsRow
              icon={networkStatus.token_required ? Lock : Eye}
              title={t('settings.networkToken')}
              description={t(
                networkStatus.token_required
                  ? 'settings.networkTokenOn'
                  : 'settings.networkTokenOff',
              )}
              testid="network-token"
            >
              <span className="font-mono text-ui-xs text-foreground/80">
                {networkStatus.token_required ? t('settings.yes') : t('settings.no')}
              </span>
            </SettingsRow>
            {networkStatus.setup_mode && (
              <SettingsRow
                icon={Lock}
                title={t('settings.networkSetupTitle')}
                description={t('settings.networkSetupHint')}
                testid="network-setup"
              />
            )}
          </SettingsGroup>

          <SettingsGroup icon={Share2} title={t('settings.networkGroupShares')}>
            <SettingsRow
              icon={FileKey2}
              title={t('settings.networkRoots')}
              description={networkStatus.file_roots.join(' · ')}
              testid="network-roots"
            />
            <SettingsRow
              icon={Globe}
              title={t('settings.networkProxy')}
              description={
                networkStatus.proxy_extra_ports.length
                  ? t('settings.networkProxyOn', {
                      ports: networkStatus.proxy_extra_ports.join(', '),
                    })
                  : t('settings.networkProxyOff')
              }
              testid="network-proxy"
            >
              <span className="font-mono text-ui-xs text-foreground/80">
                {networkStatus.proxy_extra_ports.join(', ') || '—'}
              </span>
            </SettingsRow>
            <SettingsRow
              icon={networkStatus.allow_private_fetches ? Globe : Lock}
              title={t('settings.networkPrivate')}
              description={t(
                networkStatus.allow_private_fetches
                  ? 'settings.networkPrivateOn'
                  : 'settings.networkPrivateOff',
              )}
              testid="network-private"
            >
              <span className="font-mono text-ui-xs text-foreground/80">
                {networkStatus.allow_private_fetches ? t('settings.yes') : t('settings.no')}
              </span>
            </SettingsRow>
          </SettingsGroup>

          <p className="text-ui-xs text-ink-faint" data-testid="network-fixed-note">
            {t('settings.networkFixed')}
          </p>
        </div>
      )}
    </div>
  )
}
