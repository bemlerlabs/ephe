import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWindowFocused, isWindowFocused } from '@/hooks/useWindowFocused'

/** [F6] Basis: focus detection has to see tab switches AND window blur. */
function setHidden(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
}

describe('useWindowFocused ([F6] Visibility-Gate)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    setHidden('visible')
  })

  it('initially visible in jsdom (visibilityState visible and hasFocus)', () => {
    vi.spyOn(document, 'hasFocus').mockReturnValue(true)
    const { result } = renderHook(() => useWindowFocused())
    expect(result.current).toBe(true)
    expect(isWindowFocused()).toBe(true)
  })

  it('visibilitychange to hidden gives false, back to visible gives true', () => {
    vi.spyOn(document, 'hasFocus').mockReturnValue(true)
    const { result } = renderHook(() => useWindowFocused())
    act(() => {
      setHidden('hidden')
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(result.current).toBe(false)
    act(() => {
      setHidden('visible')
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(result.current).toBe(true)
  })

  it('window blur gives false, focus gives true (another window on top)', () => {
    const hasFocus = vi.spyOn(document, 'hasFocus')
    const { result } = renderHook(() => useWindowFocused())
    act(() => {
      hasFocus.mockReturnValue(false)
      window.dispatchEvent(new Event('blur'))
    })
    expect(result.current).toBe(false)
    act(() => {
      hasFocus.mockReturnValue(true)
      window.dispatchEvent(new Event('focus'))
    })
    expect(result.current).toBe(true)
  })
})
