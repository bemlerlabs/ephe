/**
 * Poll discipline for the system metrics (finding of the 2026-10-02 deep test).
 *
 * useSystemMetrics reloaded every 5s through setInterval — even while the tab was
 * hidden. Guard: visible = the poll runs, hidden = stop, visible again = an
 * immediate reload plus resume.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSystemMetrics } from '@/components/dashboard/MetricsGauges'

let calls = 0
function setHidden(v: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => v })
}

describe('useSystemMetrics — visibility-gated poll', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    calls = 0
    setHidden(false)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls++
        return {
          ok: true,
          json: async () => ({
            available: true,
            cpu_percent: 10,
            mem_used_mb: 100,
            mem_percent: 20,
            disk_free_bytes: 1,
            disk_free_gb: 1,
            disk_percent: 50,
            uptime_s: 1,
          }),
        }
      }),
    )
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('laedt sofort und pollt alle 5s, solange sichtbar', () => {
    renderHook(() => useSystemMetrics())
    act(() => void Promise.resolve())
    expect(calls).toBe(1)
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(calls).toBe(2)
  })

  it('stoppt den Poll, wenn der Tab versteckt wird, und resume bei sichtbar', () => {
    renderHook(() => useSystemMetrics())
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(calls).toBe(2)
    // hide the tab -> no further polling
    setHidden(true)
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    act(() => {
      vi.advanceTimersByTime(20000)
    })
    expect(calls).toBe(2)
    // visible again -> one immediate reload, then resume
    setHidden(false)
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(calls).toBe(3)
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(calls).toBe(4)
  })
})
