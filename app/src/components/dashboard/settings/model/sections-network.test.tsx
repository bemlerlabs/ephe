// I6-6: the network area — a read-out of the live state, never a control.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { NetworkSection } from './sections-network'
import type { SettingsModel } from './types'
import type { NetworkStatus } from '@/lib/api'

const local: NetworkStatus = {
  bind_host: '127.0.0.1',
  bind_port: 8765,
  lan: false,
  setup_mode: false,
  token_required: false,
  file_roots: ['/Users/x/Downloads', '/tmp'],
  proxy_extra_ports: [],
  allow_private_fetches: false,
}

function model(status: NetworkStatus | null) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    networkStatus: status,
  } as unknown as SettingsModel
}

describe('NetworkSection', () => {
  it('zeigt Bind, Reichweite und Token aus dem Payload', () => {
    render(<NetworkSection model={model(local)} />)
    expect(screen.getByTestId('network-status')).toBeTruthy()
    expect(screen.getByTestId('network-bind').textContent).toContain('127.0.0.1:8765')
    expect(screen.getByTestId('network-reach').textContent).toContain('settings.networkReachLocal')
    expect(screen.getByTestId('network-token').textContent).toContain('settings.networkTokenOff')
  })

  it('ein LAN-Start sagt Reichweite und Token, was sie sind', () => {
    render(
      <NetworkSection
        model={model({ ...local, bind_host: '0.0.0.0', lan: true, token_required: true })}
      />,
    )
    expect(screen.getByTestId('network-reach').textContent).toContain('settings.networkReachLan')
    expect(screen.getByTestId('network-token').textContent).toContain('settings.networkTokenOn')
  })

  it('die Freigabe-Ordner sind die gelesene Liste, nicht eine getippte', () => {
    render(<NetworkSection model={model(local)} />)
    const row = screen.getByTestId('network-roots')
    expect(row.textContent).toContain('/Users/x/Downloads')
    expect(row.textContent).toContain('/tmp')
  })

  it('Port-Freigaben zeigen nur, was ausdrucklich gesetzt ist', () => {
    const { unmount } = render(<NetworkSection model={model(local)} />)
    expect(screen.getByTestId('network-proxy').textContent).toContain('settings.networkProxyOff')
    unmount()
    render(
      <NetworkSection
        model={model({ ...local, proxy_extra_ports: ['6379'], allow_private_fetches: true })}
      />,
    )
    expect(screen.getByTestId('network-proxy').textContent).toContain('"ports":"6379"')
    expect(screen.getByTestId('network-private').textContent).toContain('settings.networkPrivateOn')
  })

  it('sagt, wo die Werte gesetzt werden, und hat keinen Knopf', () => {
    const { container } = render(<NetworkSection model={model(local)} />)
    expect(screen.getByTestId('network-fixed-note').textContent).toContain('settings.networkFixed')
    expect(container.querySelector('button')).toBeNull()
    expect(container.querySelector('input')).toBeNull()
  })

  it('ohne Status: Ladezeile statt erfundener Adresse', () => {
    render(<NetworkSection model={model(null)} />)
    expect(screen.getByTestId('network-loading').textContent).toContain('settings.networkLoading')
    expect(screen.queryByTestId('network-bind')).toBeNull()
  })
})
