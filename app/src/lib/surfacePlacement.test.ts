/**
 * Seam C, first cut — the placement `components.ui.type` asks for, on both halves.
 *
 * The manifest names one of three types and the shell owns every placement they resolve
 * to. These cases pin the table: a `floating-window` gets the desktop's own window only
 * where a window exists, a `canvas-overlay` is the frame on both halves, and a
 * `dock-panel` is a coded refusal until the docked region lands — never a silent
 * fallback to a frame. A type outside the vocabulary is refused the same way, because a
 * descriptor a manifest validator never saw is still not something to guess at.
 */
import { describe, expect, it } from 'vitest'
import { resolveSurfacePlacement, type SurfaceType } from './surfacePlacement'

const DESKTOP = { isDesktop: true }
const BROWSER = { isDesktop: false }
const TYPES: SurfaceType[] = ['floating-window', 'dock-panel', 'canvas-overlay']

describe('a floating-window', () => {
  it('takes the desktop window where the shell has one', () => {
    expect(resolveSurfacePlacement('floating-window', DESKTOP)).toEqual({
      kind: 'native',
      refusal: null,
    })
  })

  it('takes the overlay stack in a browser tab, which has no window to give', () => {
    expect(resolveSurfacePlacement('floating-window', BROWSER)).toEqual({
      kind: 'overlay',
      refusal: null,
    })
  })
})

describe('a canvas-overlay', () => {
  it('is a frame on the desktop, not a refusal the shell used to answer with', () => {
    expect(resolveSurfacePlacement('canvas-overlay', DESKTOP)).toEqual({
      kind: 'canvas-overlay',
      refusal: null,
    })
  })

  it('is the same frame in a browser tab', () => {
    expect(resolveSurfacePlacement('canvas-overlay', BROWSER)).toEqual({
      kind: 'canvas-overlay',
      refusal: null,
    })
  })
})

describe('a dock-panel', () => {
  it('is refused with a code in a browser tab instead of floating as a frame', () => {
    const resolved = resolveSurfacePlacement('dock-panel', BROWSER)
    expect(resolved.kind).toBe('refused')
    if (resolved.kind !== 'refused') return
    expect(resolved.refusal.reason_code).toBe('surface_dock_panel_unavailable')
    expect(resolved.refusal.next).toContain('floating-window')
    expect(resolved.refusal.next).toContain('canvas-overlay')
  })

  it('is refused the same way on the desktop', () => {
    const resolved = resolveSurfacePlacement('dock-panel', DESKTOP)
    expect(resolved.kind).toBe('refused')
    if (resolved.kind !== 'refused') return
    expect(resolved.refusal.reason_code).toBe('surface_dock_panel_unavailable')
  })
})

describe('the refusal envelope', () => {
  it('carries exactly the code and the move, so a caller can branch on it', () => {
    const resolved = resolveSurfacePlacement('dock-panel', BROWSER)
    if (resolved.kind !== 'refused') throw new Error('dock-panel resolved to a placement')
    expect(Object.keys(resolved.refusal).sort()).toEqual(['next', 'reason_code'])
    expect(typeof resolved.refusal.reason_code).toBe('string')
    expect(resolved.refusal.next.length).toBeGreaterThan(0)
  })

  it('refuses a type outside the declared vocabulary instead of guessing a shape', () => {
    const resolved = resolveSurfacePlacement('side-panel', BROWSER)
    expect(resolved.kind).toBe('refused')
    if (resolved.kind !== 'refused') return
    expect(resolved.refusal.reason_code).toBe('surface_type_unknown')
    expect(resolved.refusal.next).toContain('components.ui.type')
  })
})

describe('the desktop window', () => {
  it('is only ever what a floating-window asked for', () => {
    for (const type of TYPES) {
      const resolved = resolveSurfacePlacement(type, DESKTOP)
      expect(resolved.kind === 'native').toBe(type === 'floating-window')
    }
  })
})
