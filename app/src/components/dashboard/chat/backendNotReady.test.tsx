/**
 * Issue #193: a window without a backend may not present a live composer.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BackendNotReady from '@/components/shell/BackendNotReady'

describe('the statement a window without a backend makes', () => {
  it('names the state and the one action, both visible', () => {
    render(
      <BackendNotReady
        readiness={{
          ready: false,
          state: 'unconfigured',
          port: 8765,
          baseUrl: 'http://127.0.0.1:8765',
          config: '/home/read/.ephe/desktop.json',
          sentence: 'No backend is configured for this window.',
          action: 'Run `ephe desktop` to let the app start one.',
        }}
      />,
    )
    const banner = screen.getByTestId('backend-not-ready')
    expect(banner.textContent).toContain('No backend is configured')
    expect(banner.textContent).toContain('ephe desktop')
  })
})
