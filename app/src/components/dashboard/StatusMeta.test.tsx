import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'minutes' in opts ? `${key}:${opts.minutes}` : key,
  }),
}))

import { ToolbarMeta } from './StatusMeta'

const metricsResponse = () => ({
  ok: true,
  json: async () => ({
    available: true,
    cpu_percent: 27.4,
    mem_used_mb: 1822,
    mem_percent: 41.0,
    disk_free_bytes: 1_073_741_824_000,
    disk_free_gb: 1000.0,
    disk_percent: 15.0,
    uptime_s: 480,
  }),
})

describe('ToolbarMeta (status popover)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => metricsResponse()),
    )
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows uptime and free disk once metrics arrive', async () => {
    render(<ToolbarMeta sessionId="s1" />)
    await waitFor(() => {
      expect(screen.getByTestId('toolbar-meta').textContent).toContain('toolbar.uptimeShort:8')
      expect(screen.getByTestId('toolbar-meta').textContent).toContain('metrics.freeGb')
    })
  })

  it('autospeak toggle persists to the per-session key', async () => {
    render(<ToolbarMeta sessionId="s1" />)
    const btn = await waitFor(() => screen.getByTestId('toolbar-autospeak'))
    fireEvent.click(btn)
    expect(localStorage.getItem('ephe.autospeak.session.s1')).toBe('1')
    expect(btn.getAttribute('aria-pressed')).toBe('true')
  })
})
