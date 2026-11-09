/**
 * W1-4 — the geometry and the stack of the overlay windows, without a DOM.
 *
 * The overlay is the browser half of the same surface the desktop half (W1-3)
 * puts in a window of its own label, and both halves agree on the two decisions
 * the stack owns: one surface per plugin, and a viewport the geometry is clamped
 * against. Every operation here is a function from state to state, so the edge
 * cases — a plugin opened twice, a restore into a window that has since shrunk, a
 * focus that reshuffles the stack — are arithmetic a reader can check, with no
 * `getBoundingClientRect` and no layout engine in the room to agree with.
 */
import { describe, expect, it } from 'vitest'
import {
  clampRect,
  closeSurface,
  EMPTY_STACK,
  findSurface,
  focusSurface,
  minimizeSurface,
  moveSurface,
  openSurface,
  retargetSurface,
  OVERLAY_RAIL_HEIGHT,
  OVERLAY_SURFACE_MIN,
  restoreSurface,
  resizeSurface,
  stackOrder,
  surfaceKey,
  topSurface,
  type OverlayStack,
  type SurfaceSpec,
  type Viewport,
} from './overlayModel'

const DESKTOP: Viewport = { width: 1440, height: 900 }
const PHONE: Viewport = { width: 360, height: 640 }

function spec(over: Partial<SurfaceSpec> = {}): SurfaceSpec {
  return {
    pluginId: 'acme-countdown',
    title: 'Countdown',
    surfaceType: 'floating-window',
    url: 'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/',
    width: 360,
    height: 240,
    transparent: false,
    ...over,
  }
}

const open = (
  over: Partial<SurfaceSpec> = {},
  viewport = DESKTOP,
  stack: OverlayStack = EMPTY_STACK,
) => openSurface(stack, spec(over), viewport).stack

describe('the key of a surface', () => {
  it('is the same string for the same plugin, every time', () => {
    expect(surfaceKey('acme-countdown')).toBe(surfaceKey('acme-countdown'))
    expect(surfaceKey('acme-countdown')).toContain('acme-countdown')
  })

  it('separates two plugins', () => {
    expect(surfaceKey('acme-countdown')).not.toBe(surfaceKey('acme-timer'))
  })
})

describe('opening a surface', () => {
  it('places the descriptor default inside the viewport and puts it on top', () => {
    const stack = open()
    const surface = findSurface(stack, surfaceKey('acme-countdown'))
    expect(surface).toBeDefined()
    expect(surface?.bounds.width).toBe(360)
    expect(surface?.bounds.height).toBe(240)
    expect(surface?.z).toBeGreaterThan(0)
    expect(surface?.url).toContain('/api/plugins/ui/acme-countdown/n0nce/')
    expect(surface?.minimized).toBe(false)
  })

  it('uses a saved host box instead of the cascade', () => {
    const stack = openSurface(EMPTY_STACK, spec(), DESKTOP, {
      x: 40,
      y: 64,
      width: 300,
      height: 200,
    }).stack
    expect(findSurface(stack, surfaceKey('acme-countdown'))?.bounds).toEqual({
      x: 40,
      y: 64,
      width: 300,
      height: 200,
    })
  })

  it('keeps the whole window inside a viewport smaller than the default size', () => {
    const stack = open({ width: 800, height: 600 }, PHONE)
    const bounds = findSurface(stack, surfaceKey('acme-countdown'))?.bounds
    expect(bounds).toMatchObject({ x: 0, width: 360, height: 600 })
    expect(bounds!.y).toBeGreaterThanOrEqual(0)
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(PHONE.height)
  })

  it('never shrinks a surface below the floor the controls need', () => {
    const stack = open({ width: 40, height: 20 })
    const bounds = findSurface(stack, surfaceKey('acme-countdown'))?.bounds
    expect(bounds!.width).toBe(OVERLAY_SURFACE_MIN.width)
    expect(bounds!.height).toBe(OVERLAY_SURFACE_MIN.height)
  })

  it('reports the second open of the same plugin as a reveal', () => {
    const first = openSurface(EMPTY_STACK, spec(), DESKTOP)
    const second = openSurface(first.stack, spec({ width: 900, height: 700 }), DESKTOP)
    expect(first.created).toBe(true)
    expect(second.created).toBe(false)
    expect(second.stack.surfaces).toHaveLength(1)
  })

  /// The desktop twin answers the same way: `ephe-plugin-<id>` is one label, and
  /// W1-3 measured the second open as `created=false` with one window on screen.
  /// A re-open that re-derived the geometry would move a window the user parked.
  it('keeps the placement the user made when the plugin is opened again', () => {
    const stack = moveSurface(open(), surfaceKey('acme-countdown'), { x: 120, y: 90 }, DESKTOP)
    const again = openSurface(stack, spec({ width: 900 }), DESKTOP)
    expect(findSurface(again.stack, surfaceKey('acme-countdown'))?.bounds).toEqual({
      x: 120,
      y: 90,
      width: 360,
      height: 240,
    })
  })

  it('keeps the placement when a dead credential is replaced', () => {
    const stack = moveSurface(open(), surfaceKey('acme-countdown'), { x: 120, y: 90 }, DESKTOP)
    const next = retargetSurface(
      stack,
      'acme-countdown',
      'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/fresh/',
    )
    const surface = findSurface(next, surfaceKey('acme-countdown'))
    expect(surface?.url).toBe('http://127.0.0.1:8765/api/plugins/ui/acme-countdown/fresh/')
    expect(surface?.bounds).toEqual({ x: 120, y: 90, width: 360, height: 240 })
  })

  it('reveals and raises a minimized surface on re-open', () => {
    const minimized = minimizeSurface(open(), surfaceKey('acme-countdown'))
    const other = open({ pluginId: 'acme-timer' }, DESKTOP, minimized)
    const again = openSurface(other, spec(), DESKTOP)
    const surface = findSurface(again.stack, surfaceKey('acme-countdown'))
    expect(again.created).toBe(false)
    expect(surface?.minimized).toBe(false)
    expect(stackOrder(again.stack)).toEqual(['overlay:acme-timer', 'overlay:acme-countdown'])
  })

  it('cascades two plugins so both title rails are reachable', () => {
    const stack = open({ pluginId: 'acme-timer' }, DESKTOP, open())
    const [a, b] = stack.surfaces
    expect(a!.bounds).not.toEqual(b!.bounds)
    expect(b!.bounds.x).toBeGreaterThan(a!.bounds.x)
  })
})

describe('the stack order', () => {
  it('puts a focused surface on top, last', () => {
    let stack = open({ pluginId: 'a' })
    stack = open({ pluginId: 'b' }, DESKTOP, stack)
    stack = open({ pluginId: 'c' }, DESKTOP, stack)
    expect(stackOrder(stack)).toEqual(['overlay:a', 'overlay:b', 'overlay:c'])
    stack = focusSurface(stack, surfaceKey('a'))
    expect(stackOrder(stack)).toEqual(['overlay:b', 'overlay:c', 'overlay:a'])
    expect(topSurface(stack)?.pluginId).toBe('a')
  })

  it('leaves the stack alone when the top surface is focused again', () => {
    const stack = open()
    const refocused = focusSurface(stack, surfaceKey('acme-countdown'))
    expect(refocused).toBe(stack)
  })

  /// Raise so the surface is where the user left it when the dock hands it back,
  /// keep the state the gesture that minimizes is meant to keep.
  it('raises a minimized surface without un-minimizing it', () => {
    let stack = open({ pluginId: 'a' })
    stack = open({ pluginId: 'b' }, DESKTOP, stack)
    const minimized = minimizeSurface(stack, surfaceKey('a'))
    const focused = focusSurface(minimized, surfaceKey('a'))
    expect(topSurface(focused)?.pluginId).toBe('a')
    expect(findSurface(focused, surfaceKey('a'))?.minimized).toBe(true)
  })

  it('never reuses a z step, so a closed surface cannot be stood in for', () => {
    let stack = open({ pluginId: 'a' })
    const firstZ = topSurface(stack)!.z
    stack = closeSurface(stack, surfaceKey('a'))
    stack = open({ pluginId: 'b' }, DESKTOP, stack)
    expect(topSurface(stack)!.z).toBeGreaterThan(firstZ)
  })

  it('keeps the surfaces below an unharmed when the top one closes', () => {
    let stack = open({ pluginId: 'a' })
    stack = open({ pluginId: 'b' }, DESKTOP, stack)
    const closed = closeSurface(stack, surfaceKey('b'))
    expect(closed.surfaces.map((s) => s.pluginId)).toEqual(['a'])
    expect(findSurface(closed, surfaceKey('b'))).toBeUndefined()
  })
})

describe('moving, resizing and restoring against the viewport', () => {
  it('keeps a dragged window whole inside the viewport', () => {
    const key = surfaceKey('acme-countdown')
    const moved = moveSurface(open(), key, { x: 4000, y: -900 }, DESKTOP)
    const bounds = findSurface(moved, key)!.bounds
    expect(bounds.x).toBe(DESKTOP.width - bounds.width)
    expect(bounds.y).toBe(0)
  })

  /// Only the rail of a minimized surface is on screen, and it is 44 px tall:
  /// clamping the stored box would park a live rail off the bottom of the window.
  /// The size the user set survives the gesture, so the restore has something to
  /// put back.
  it('keeps the title rail inside even when the body hangs below', () => {
    const key = surfaceKey('acme-countdown')
    const minimized = minimizeSurface(open(), key)
    expect(findSurface(minimized, key)!.bounds.height).toBe(240)
    const moved = moveSurface(minimized, key, { x: 0, y: 10_000 }, DESKTOP)
    expect(findSurface(moved, key)!.bounds.y).toBe(DESKTOP.height - OVERLAY_RAIL_HEIGHT)
    expect(findSurface(moved, key)!.bounds.height).toBe(240)
  })

  it('honours the size floor on a resize and the viewport ceiling above it', () => {
    const key = surfaceKey('acme-countdown')
    const shrunk = resizeSurface(open(), key, { width: 10, height: 10 }, DESKTOP)
    expect(findSurface(shrunk, key)!.bounds).toEqual({
      x: expect.any(Number),
      y: expect.any(Number),
      width: OVERLAY_SURFACE_MIN.width,
      height: OVERLAY_SURFACE_MIN.height,
    })
    const grown = resizeSurface(shrunk, key, { width: 5000, height: 5000 }, DESKTOP)
    expect(findSurface(grown, key)!.bounds).toEqual({
      x: 0,
      y: 0,
      width: DESKTOP.width,
      height: DESKTOP.height,
    })
  })

  /// The defect this case holds: the user parks a widget at the right edge of a
  /// wide window, the window is later narrowed, and the restore puts it back at a
  /// coordinate nobody can reach.
  it('brings a surface back inside the viewport when restore follows a shrink', () => {
    const key = surfaceKey('acme-countdown')
    const parked = moveSurface(open(), key, { x: 1050, y: 640 }, DESKTOP)
    const minimized = minimizeSurface(parked, key)
    const restored = restoreSurface(minimized, key, PHONE)
    const bounds = findSurface(restored, key)!.bounds
    expect(findSurface(restored, key)!.minimized).toBe(false)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(PHONE.width)
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(PHONE.height)
    expect(bounds.width).toBeLessThanOrEqual(PHONE.width)
  })

  it('puts focus and the raise behind a restore', () => {
    const key = surfaceKey('a')
    let stack = open({ pluginId: 'a' })
    stack = open({ pluginId: 'b' }, DESKTOP, stack)
    const before = topSurface(stack)!.z
    const restored = restoreSurface(minimizeSurface(stack, key), key, DESKTOP)
    expect(topSurface(restored)!.pluginId).toBe('a')
    expect(topSurface(restored)!.z).toBeGreaterThan(before)
  })
})

describe('operations on a surface that is not in the stack', () => {
  const key = surfaceKey('gone')

  it('answer with the stack they were given', () => {
    const stack = open()
    for (const next of [
      closeSurface(stack, key),
      focusSurface(stack, key),
      minimizeSurface(stack, key),
      restoreSurface(stack, key, DESKTOP),
      moveSurface(stack, key, { x: 1, y: 1 }, DESKTOP),
      resizeSurface(stack, key, { width: 400, height: 300 }, DESKTOP),
    ]) {
      expect(next).toBe(stack)
    }
  })

  it('leave an empty stack empty', () => {
    expect(topSurface(EMPTY_STACK)).toBeNull()
    expect(stackOrder(EMPTY_STACK)).toEqual([])
    expect(closeSurface(EMPTY_STACK, key)).toBe(EMPTY_STACK)
  })
})

describe('clampRect', () => {
  it('is the one place the floor and the ceiling are decided', () => {
    expect(clampRect({ x: -50, y: -50, width: 100, height: 100 }, DESKTOP)).toEqual({
      x: 0,
      y: 0,
      width: OVERLAY_SURFACE_MIN.width,
      height: OVERLAY_SURFACE_MIN.height,
    })
    expect(clampRect({ x: 0, y: 0, width: 200, height: 200 }, { width: 100, height: 100 })).toEqual(
      { x: 0, y: 0, width: 100, height: 100 },
    )
  })

  it('does not move a rect that already fits', () => {
    const rect = { x: 40, y: 60, width: 360, height: 240 }
    expect(clampRect(rect, DESKTOP)).toEqual(rect)
  })

  it('never leaves a rail taller than the viewport it is clamped into', () => {
    const clamped = clampRect({ x: 0, y: 0, width: 900, height: 900 }, { width: 1200, height: 60 })
    expect(clamped.height).toBe(60)
    expect(clamped.y).toBe(0)
  })
})
