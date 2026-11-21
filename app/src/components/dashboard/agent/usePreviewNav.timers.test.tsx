// @vitest-environment jsdom
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { usePreviewNav } from './usePreviewNav'
import type { Tab, TabState } from './primitives'

/**
 * Unmounting must cancel the deferred focus.
 *
 * The hook focuses the address bar 40–60 ms after a navigation so the panel can
 * mount first. Those timers used to be owned by nobody: after the component was
 * gone the callback still ran and read `document.activeElement`, which is how CI's
 * frontend suite died — 1417 tests passed and the file still failed with
 * `ReferenceError: document is not defined`, thrown from `usePreviewNav.ts:103`
 * during timer teardown. Locally the run finished before the callback was due, so
 * only the machine that was busy showed it.
 *
 * The assertion is therefore about the pending timer, not about focus: a component
 * that leaves work scheduled after unmount is the bug, whatever the callback does.
 */
function Probe() {
  const host = {
    open: true,
    setOpen: () => {},
    tabState: { tabs: [], active: null } as unknown as TabState,
    openTab: (_key: Tab) => {},
  }
  usePreviewNav(host)
  return <input aria-label="probe-address" />
}

describe('usePreviewNav deferred focus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('cancels its pending focus when the component unmounts', () => {
    const { unmount } = render(<Probe />)

    act(() => {
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: 'https://ephe.dev' } }),
      )
    })
    expect(vi.getTimerCount()).toBeGreaterThan(0)

    unmount()

    expect(vi.getTimerCount()).toBe(0)
    expect(() => act(() => vi.advanceTimersByTime(200))).not.toThrow()
  })

  it('still focuses while the component is mounted', () => {
    // The guard against over-cleaning: the deferred focus is a feature (the panel
    // needs its frame first), so a mounted component must still run it.
    const { container } = render(<Probe />)
    act(() => {
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: 'https://ephe.dev' } }),
      )
    })
    act(() => {
      vi.advanceTimersByTime(120)
    })
    expect(vi.getTimerCount()).toBe(0)
    expect(container.querySelector('input')).toBeInTheDocument()
  })
})
