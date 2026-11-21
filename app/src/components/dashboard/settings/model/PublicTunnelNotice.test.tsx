// The public hop, said out loud: the offer before the tunnel, the reason after a
// refusal, the clock while one stands.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { PublicTunnelNotice } from './PublicTunnelNotice'
import { renderMobile } from './sections-io'
import type { SettingsModel } from './types'
import type { MobileQR } from '@/lib/api'

vi.mock('../../TelegramPairingCard', () => ({ TelegramPairingCard: () => null }))
vi.mock('../../DiscordChannelCard', () => ({ DiscordChannelCard: () => null }))

const t = ((key: string, opts?: Record<string, unknown>) =>
  opts ? `${key} ${JSON.stringify(opts)}` : key) as SettingsModel['t']

const base: MobileQR = {
  url: 'http://10.0.0.9:8765/mobile.html',
  qr_base64: 'QUJD',
  mode: 'lan',
  is_public: false,
  requires_internet: false,
  lan_reachable: false,
  message: 'settings.mobileFirewallHint',
}

function notice(qr: Partial<MobileQR>, onPublic = vi.fn()) {
  return render(<PublicTunnelNotice qr={{ ...base, ...qr }} t={t} onPublic={onPublic} />)
}

describe('PublicTunnelNotice', () => {
  it('GIVEN a LAN the phone cannot reach WHEN the answer offers public mode THEN it asks before it publishes', () => {
    notice({ public_offer: true })

    expect(screen.getByText('settings.mobilePublicOffer')).toBeInTheDocument()
    expect(screen.getByTestId('mobile-public-open').textContent).toContain(
      'settings.mobilePublicOpen',
    )
  })

  it('GIVEN the offer WHEN the operator takes it THEN public mode is asked for by name', () => {
    const onPublic = vi.fn()
    notice({ public_offer: true }, onPublic)

    fireEvent.click(screen.getByTestId('mobile-public-open'))

    expect(onPublic).toHaveBeenCalledTimes(1)
  })

  it('GIVEN a working LAN WHEN nothing is offered THEN the public path is not mentioned', () => {
    notice({ lan_reachable: true, message: '', public_offer: false })

    expect(screen.queryByTestId('mobile-public-open')).not.toBeInTheDocument()
    expect(screen.queryByText('settings.mobilePublicOffer')).not.toBeInTheDocument()
  })

  it('GIVEN a standing hop WHEN it reports its clock THEN it says how long it has run and when it ends', () => {
    notice({
      is_public: true,
      requires_internet: true,
      mode: 'public',
      url: 'https://a1b2c3.lhr.life/mobile.html',
      message: '',
      tunnel_uptime_seconds: 90,
      tunnel_stops_in_seconds: 1710,
    })

    const exposure = screen.getByTestId('mobile-public-exposure')
    expect(exposure.textContent).toContain('settings.mobilePublicExposure')
    expect(exposure.textContent).toContain('"up":2')
    expect(exposure.textContent).toContain('"idle":29')
  })

  it('GIVEN a hop that reports no clock WHEN it renders THEN no idle promise is made', () => {
    notice({
      is_public: true,
      requires_internet: true,
      mode: 'public',
      message: '',
      tunnel_uptime_seconds: null,
      tunnel_stops_in_seconds: null,
    })

    expect(screen.queryByTestId('mobile-public-exposure')).not.toBeInTheDocument()
  })

  it('GIVEN a refusal that names the host key WHEN it arrives THEN the surface says which key is missing', () => {
    notice({ tunnel_block: 'host_key_unverified' })

    expect(screen.getByTestId('mobile-public-block').textContent).toContain(
      'settings.mobilePublicBlockedHostKey',
    )
  })

  it('GIVEN a refusal that names the missing ssh client WHEN it arrives THEN the surface says that', () => {
    notice({ tunnel_block: 'ssh_missing' })

    expect(screen.getByTestId('mobile-public-block').textContent).toContain(
      'settings.mobilePublicBlockedSshMissing',
    )
  })

  it('GIVEN a refusal the surface has no words for WHEN it arrives THEN a plain refusal still shows', () => {
    notice({ tunnel_block: 'something_new' })

    expect(screen.getByTestId('mobile-public-block').textContent).toBe(
      'settings.mobilePublicBlocked',
    )
  })

  it('GIVEN the pairing group WHEN the answer offers the hop THEN the group carries the notice', async () => {
    const loadMobileQR = vi.fn()
    const model = {
      t,
      i18n: { language: 'de' },
      loadMobileQR,
      mobileQR: { ...base, public_offer: true },
      mobileLoading: false,
      mobileError: null,
      mobileConnected: false,
    } as unknown as SettingsModel

    render(<div>{renderMobile(model)}</div>)

    fireEvent.click(await screen.findByTestId('mobile-public-open'))

    expect(loadMobileQR).toHaveBeenCalledWith('public')
  })
})
