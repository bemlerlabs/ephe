// WS-E 47 — tab persistence. The panel promises "a restart reopens the same
// pages"; tab and recent restore, but activeTab was written as a bare string
// while readJson expected JSON, so JSON.parse threw and the restart reopened the
// first page. These tests pin the restore, including the round trip.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTabRegistry } from './useTabRegistry'

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
}))

describe('useTabRegistry — restore across a restart', () => {
  beforeEach(() => localStorage.clear())

  it('restores the stored active tab (bare form) instead of the first page', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'git']))
    localStorage.setItem('ephe.panel.activeTab', 'git')
    const { result } = renderHook(() => useTabRegistry())
    expect(result.current.tabState.open).toEqual(['preview', 'git'])
    expect(result.current.tabState.active).toBe('git')
  })

  it('accepts the JSON form too', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'terminal']))
    localStorage.setItem('ephe.panel.activeTab', '"terminal"')
    const { result } = renderHook(() => useTabRegistry())
    expect(result.current.tabState.active).toBe('terminal')
  })

  it('aliases the retired browser key and falls back when the tab is not open', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    localStorage.setItem('ephe.panel.activeTab', 'browser')
    const first = renderHook(() => useTabRegistry())
    expect(first.result.current.tabState.active).toBe('preview')

    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview', 'terminal']))
    localStorage.setItem('ephe.panel.activeTab', 'git')
    const second = renderHook(() => useTabRegistry())
    expect(second.result.current.tabState.active).toBe('preview')
  })

  it('with nothing stored, the first page is active', () => {
    const { result } = renderHook(() => useTabRegistry())
    expect(result.current.tabState.open).toEqual(['preview'])
    expect(result.current.tabState.active).toBe('preview')
  })

  it('round trip: the page that was active is the one a new boot opens', () => {
    localStorage.setItem('ephe.panel.tabs', JSON.stringify(['preview']))
    const first = renderHook(() => useTabRegistry())
    act(() => first.result.current.openTab('memory'))
    expect(first.result.current.tabState.active).toBe('memory')
    first.unmount()

    const second = renderHook(() => useTabRegistry())
    expect(second.result.current.tabState.open).toEqual(['preview', 'memory'])
    expect(second.result.current.tabState.active).toBe('memory')
  })
})
