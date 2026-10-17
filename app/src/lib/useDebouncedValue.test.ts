/**
 * D9: the hold between a keystroke and a request.
 *
 * Both search fields sat in their own fetch effect, so a word of six letters was six
 * round trips. On the memory route each one is a vector search over the whole store;
 * measured against the running backend, typing `Kaffee` produced 6 requests for one
 * answer. The hold is by value, so a paste, a clear button and a typed letter all
 * take the same path.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useState } from 'react'
import { useDebouncedValue } from './useDebouncedValue'

function useField(initial = '') {
  const [value, setValue] = useState(initial)
  return { value, setValue, held: useDebouncedValue(value, 250) }
}

afterEach(() => vi.useRealTimers())

describe('the held value of a search field', () => {
  it('keeps the old value while the field is still moving', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useField(''))
    act(() => result.current.setValue('Kaf'))
    expect(result.current.value).toBe('Kaf')
    expect(result.current.held).toBe('')
    act(() => void vi.advanceTimersByTime(200))
    expect(result.current.held).toBe('')
    act(() => void vi.advanceTimersByTime(60))
    expect(result.current.held).toBe('Kaf')
  })

  it('collapses a typed word into the one value it ends on', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useField(''))
    for (const letter of 'Kaffee') {
      act(() => result.current.setValue((v) => v + letter))
      act(() => void vi.advanceTimersByTime(40))
    }
    // 40 ms between letters is fast typing: no timer for a prefix ever reached its
    // 250 ms, so nothing was requested until the word was done.
    expect(result.current.held).toBe('')
    act(() => void vi.advanceTimersByTime(250))
    expect(result.current.held).toBe('Kaffee')
  })

  it('settles back to empty when the field is cleared', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useField('Kaffee'))
    act(() => void vi.advanceTimersByTime(250))
    expect(result.current.held).toBe('Kaffee')
    act(() => result.current.setValue(''))
    act(() => void vi.advanceTimersByTime(250))
    expect(result.current.held).toBe('')
  })
})
