/**
 * QD-005B — proof for the one fact the setup screen owns.
 *
 * GIVEN the producer the setup route calls and the listener the companion reads
 * WHEN the card appears, is dismissed, or a surface unmounts
 * THEN  the snapshot follows the fact, each change publishes once, and a
 *       released listener hears nothing more.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'

import {
  announceSetupRepair,
  setupRepairSnapshot,
  subscribeSetupRepair,
  useSetupRepair,
} from './companionRepair'

afterEach(() => announceSetupRepair(false))

describe('companionRepair — the producer and its one listener set', () => {
  it('a repair the setup screen renders is readable without a round trip', () => {
    expect(setupRepairSnapshot()).toBe(false)
    announceSetupRepair(true)
    expect(setupRepairSnapshot()).toBe(true)
  })

  it('the hook re-renders on the announcement and drops it again', () => {
    const { result, rerender } = renderHook(() => useSetupRepair())
    expect(result.current).toBe(false)
    announceSetupRepair(true)
    rerender()
    expect(result.current).toBe(true)
    announceSetupRepair(false)
    rerender()
    expect(result.current).toBe(false)
  })

  it('a dismissed repair clears the fact for every surface', () => {
    announceSetupRepair(true)
    announceSetupRepair(false)
    expect(setupRepairSnapshot()).toBe(false)
  })

  it('publishes once per change and stops after the release', () => {
    const listener = vi.fn()
    const release = subscribeSetupRepair(listener)
    announceSetupRepair(true)
    announceSetupRepair(true)
    expect(listener).toHaveBeenCalledTimes(1)
    release()
    announceSetupRepair(false)
    announceSetupRepair(true)
    expect(listener).toHaveBeenCalledTimes(1)
  })
})
