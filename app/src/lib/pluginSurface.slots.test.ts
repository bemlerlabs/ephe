/**
 * React slots: a plugin declares where it renders, the host honors it.
 *
 * The manifest's `components.surfaces[].slot` field says "overlay", "side-panel", or
 * "tab". The surface routing reads that declaration and places the surface accordingly
 * — not by guessing from the runtime environment. A plugin that declares `slot:
 * "side-panel"` renders in the side panel even on desktop, where the default would be
 * a native window.
 */
import { describe, expect, it } from 'vitest'
import { resolveSurfaceSlot, type SurfaceSlot } from './pluginSurface'

describe('resolveSurfaceSlot', () => {
  it('returns the declared slot when the manifest specifies one', () => {
    const declared: SurfaceSlot = 'side-panel'
    const resolved = resolveSurfaceSlot(declared, { isDesktop: true })
    expect(resolved).toBe('side-panel')
  })

  it('falls back to native on desktop when no slot is declared', () => {
    const resolved = resolveSurfaceSlot(undefined, { isDesktop: true })
    expect(resolved).toBe('native')
  })

  it('falls back to overlay in the browser when no slot is declared', () => {
    const resolved = resolveSurfaceSlot(undefined, { isDesktop: false })
    expect(resolved).toBe('overlay')
  })

  it('honors the declared slot even when it contradicts the runtime default', () => {
    // A plugin declares "overlay" on desktop — the host respects the declaration
    const resolved = resolveSurfaceSlot('overlay', { isDesktop: true })
    expect(resolved).toBe('overlay')
  })

  it('accepts all three slot names', () => {
    expect(resolveSurfaceSlot('overlay', { isDesktop: false })).toBe('overlay')
    expect(resolveSurfaceSlot('native', { isDesktop: true })).toBe('native')
    expect(resolveSurfaceSlot('side-panel', { isDesktop: true })).toBe('side-panel')
  })
})
