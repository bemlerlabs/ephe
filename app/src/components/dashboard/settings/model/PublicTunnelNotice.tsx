/**
 * The public hop, said out loud. The pairing group shows this block in three cases:
 * the answer offers the tunnel, a request for one came back refused, or a hop is
 * standing. The question comes before the address, the reason comes before the wait.
 */
import type { MobileQR } from '@/lib/api'
import type { SettingsModel } from './types'

const PUBLIC_BLOCK_KEYS: Record<string, string> = {
  host_key_unverified: 'settings.mobilePublicBlockedHostKey',
  ssh_missing: 'settings.mobilePublicBlockedSshMissing',
}

/** Whole minutes, at least one: the exposure line says "2 min" ahead of "0". */
function wholeMinutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60))
}

export interface PublicTunnelNoticeProps {
  qr: MobileQR
  t: SettingsModel['t']
  onPublic: () => void
}

export function PublicTunnelNotice({ qr, t, onPublic }: PublicTunnelNoticeProps) {
  const { tunnel_uptime_seconds: up, tunnel_stops_in_seconds: stops } = qr

  return (
    <>
      {qr.public_offer && (
        <div className="space-y-2">
          <p className="text-ui-xs text-ink-soft">{t('settings.mobilePublicOffer')}</p>
          <button
            onClick={onPublic}
            data-testid="mobile-public-open"
            className="w-full glass-control rounded-xl h-10 text-ui-sm font-medium text-foreground/70 hover:text-foreground hover:bg-brand/10 transition-all"
          >
            {t('settings.mobilePublicOpen')}
          </button>
        </div>
      )}
      {qr.tunnel_block && (
        <p className="text-ui-xs text-status-danger/80" data-testid="mobile-public-block">
          {t(PUBLIC_BLOCK_KEYS[qr.tunnel_block] ?? 'settings.mobilePublicBlocked')}
        </p>
      )}
      {qr.is_public && up != null && stops != null && (
        <p className="text-ui-xs text-ink-faint text-center" data-testid="mobile-public-exposure">
          {t('settings.mobilePublicExposure', {
            up: wholeMinutes(up),
            idle: wholeMinutes(stops),
          })}
        </p>
      )}
    </>
  )
}
