import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getCapabilities: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ getCapabilities: api.getCapabilities }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

import { CapabilityMatrix, DetailsModeSwitch } from './CapabilityMatrix'

const t = (key: string) => key

beforeEach(() => {
  api.getCapabilities.mockReset()
})

describe('the capability matrix', () => {
  it('prints the guard count and its tools', async () => {
    api.getCapabilities.mockResolvedValue({
      subagent: { tools: ['read_file', 'web_search'], tool_count: 2, max_iterations: 8, read_only: true },
      main_agent: { read_only: false, note: 'all tools' },
    })
    render(<CapabilityMatrix t={t} />)
    await waitFor(() => {
      expect(screen.getByTestId('capability-sub-count').textContent).toBe('2 settings.capabilityTools')
    })
    expect(screen.getByTestId('capability-sub').textContent).toContain('read_file · web_search')
    expect(screen.getByTestId('capability-main').textContent).toContain('settings.capabilityWrites')
  })

  it('says the boundary is unreadable instead of inventing a number', async () => {
    api.getCapabilities.mockRejectedValue(new Error('offline'))
    render(<CapabilityMatrix t={t} />)
    await waitFor(() => {
      expect(screen.getByTestId('capability-sub-count').textContent).toBe('—')
    })
    expect(screen.getByTestId('capability-sub').textContent).toContain(
      'settings.capabilityUnknown',
    )
  })
})

describe('the details switch', () => {
  it('marks the current stage and reports the click', () => {
    const onChange = vi.fn()
    render(<DetailsModeSwitch value="collapsed" onChange={onChange} t={t} />)
    expect(screen.getByTestId('details-mode-collapsed').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('details-mode-expanded').getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(screen.getByTestId('details-mode-expanded'))
    expect(onChange).toHaveBeenCalledWith('expanded')
  })

  it('treats anything unknown as the everyday stage', () => {
    render(<DetailsModeSwitch value="mystery" onChange={vi.fn()} t={t} />)
    expect(screen.getByTestId('details-mode-collapsed').getAttribute('aria-pressed')).toBe('true')
  })
})

describe('a backend that answers with nothing useful', () => {
  it('keeps the tab alive and says the count is unknown', async () => {
    api.getCapabilities.mockResolvedValue({} as never)
    render(<CapabilityMatrix t={(k) => k} />)
    expect(await screen.findByTestId('capability-sub')).toBeTruthy()
    expect(screen.getByTestId('capability-sub-count').textContent).toBe('—')
  })
})
