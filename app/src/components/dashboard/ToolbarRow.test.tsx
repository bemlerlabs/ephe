/**
 * R26 — ToolbarRow (mockup second header line)
 *
 * GIVEN the top toolbar row
 * WHEN a tool button is clicked
 * THEN the matching AgentPanel tab opens via ephe:preview-open; the
 *      meta area shows uptime + free disk and the autospeak toggle works.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'minutes' in opts ? `${key}:${opts.minutes}` : key,
  }),
}))

import ToolbarRow, { ToolbarMeta } from './ToolbarRow'

const metricsResponse = () => ({
  ok: true,
  json: async () => ({
    available: true,
    cpu_percent: 27.4,
    mem_used_mb: 1822,
    mem_percent: 41.0,
    disk_free_bytes: 1_073_741_824_000, // ~1 TB free
    disk_free_gb: 1000.0,
    disk_percent: 15.0,
    uptime_s: 480,
  }),
})

describe('ToolbarRow (R26)', () => {
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

  it('renders the four tool buttons + the ⌘K palette button', () => {
    render(<ToolbarRow />)
    expect(screen.getByTestId('toolbar-files')).toBeTruthy()
    expect(screen.getByTestId('toolbar-preview')).toBeTruthy()
    expect(screen.getByTestId('toolbar-terminal')).toBeTruthy()
    expect(screen.getByTestId('toolbar-git')).toBeTruthy()
    expect(screen.getByTestId('toolbar-palette')).toBeTruthy()
    // The fifth chip was Steps. The plan card in the message is the one step
    // timeline; a chip here would offer a tab the panel no longer carries.
    expect(screen.queryByTestId('toolbar-tasks')).toBeNull()
  })

  it('tool click dispatches the AgentPanel tab event', () => {
    const listener = vi.fn()
    window.addEventListener('ephe:preview-open', listener)
    render(<ToolbarRow />)
    fireEvent.click(screen.getByTestId('toolbar-git'))
    expect(listener).toHaveBeenCalledTimes(1)
    const detail = (listener.mock.calls[0]![0] as CustomEvent).detail
    expect(detail.tab).toBe('git')
    window.removeEventListener('ephe:preview-open', listener)
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
