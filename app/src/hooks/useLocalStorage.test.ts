/**
 * Persisted state hook: reads once on mount, writes on every change, and
 * degrades to the initial value when the stored JSON is unreadable.
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useLocalStorage } from './useLocalStorage'

describe('useLocalStorage', () => {
  beforeEach(() => localStorage.clear())

  it('falls back to the initial value when nothing is stored', () => {
    const { result } = renderHook(() => useLocalStorage('missing', 5))
    expect(result.current[0]).toBe(5)
  })

  it('reads a stored JSON value on mount', () => {
    localStorage.setItem('k', JSON.stringify({ a: 1 }))
    const { result } = renderHook(() => useLocalStorage('k', { a: 0 }))
    expect(result.current[0]).toEqual({ a: 1 })
  })

  it('persists a direct update to storage', () => {
    const { result } = renderHook(() => useLocalStorage('n', 0))
    act(() => result.current[1](3))
    expect(result.current[0]).toBe(3)
    expect(JSON.parse(localStorage.getItem('n') as string)).toBe(3)
  })

  it('supports the updater form', () => {
    const { result } = renderHook(() => useLocalStorage('n', 10))
    act(() => result.current[1]((prev) => prev + 1))
    expect(result.current[0]).toBe(11)
  })

  it('degrades to the initial value on corrupt storage', () => {
    localStorage.setItem('bad', '{oops')
    const { result } = renderHook(() => useLocalStorage('bad', 'fallback'))
    expect(result.current[0]).toBe('fallback')
  })
})
