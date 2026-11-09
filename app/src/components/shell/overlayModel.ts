/**
 * The overlay stack — geometry, z-order and lifecycle, with no DOM in sight.
 *
 * This is the browser half of the plugin surface: the desktop half (W1-3,
 * `src-tauri/src/plugin_window.rs`) hands the same document to a window of its own
 * label. Two rules carry over from that half, because a plugin that runs on both
 * surfaces has to find the same behaviour on each:
 *
 *   - one surface per plugin. `ephe-plugin-<id>` is one label, and W1-3 measured a
 *     second open as a reveal with `created=false`; here the key is `overlay:<id>`.
 *   - geometry decided against a viewport the caller passes in. Nothing here reads
 *     `getBoundingClientRect`, so every clamp is arithmetic a test can pin.
 *
 * A sandboxed frame cannot report its own size, so the shell owns the box: the
 * rail it draws, and the iframe filled by the plugin document.
 */

export type Viewport = { width: number; height: number }

export type Rect = { x: number; y: number; width: number; height: number }

export type Size = { width: number; height: number }

/** What the caller knows when it asks for a surface: `ui_descriptor()` plus the mount URL. */
export type SurfaceSpec = {
  pluginId: string
  title: string
  surfaceType: string
  url: string
  width: number
  height: number
  transparent: boolean
}

export type OverlaySurface = SurfaceSpec & {
  /** Stable identity: the React key, the store handle and the clamp target. */
  key: string
  bounds: Rect
  z: number
  minimized: boolean
}

export type OverlayStack = {
  surfaces: OverlaySurface[]
  /** The highest z handed out so far. Monotonic: a closed surface never donates its step. */
  topZ: number
}

/** One 44 px row: the touch floor for the rail's own controls, met by its height. */
export const OVERLAY_RAIL_HEIGHT = 44

/** The smallest box that still holds two 44 px controls, a title and a line of content. */
export const OVERLAY_SURFACE_MIN: Size = { width: 220, height: 150 }

/** How far a new surface sits from the edge it opens nearest. */
const OVERLAY_EDGE = 16

/** How far each further surface steps, so stacked rails stay grabbable. */
const OVERLAY_CASCADE = 28

export const EMPTY_STACK: OverlayStack = { surfaces: [], topZ: 0 }

export const surfaceKey = (pluginId: string): string => `overlay:${pluginId}`

const between = (value: number, low: number, high: number): number =>
  Math.min(Math.max(value, low), high)

/**
 * The one clamp. A box is never larger than the viewport it lives in — the ceiling
 * wins when a short window cannot hold the floor — and never partly outside it. `y`
 * is bounded by the height a *minimized* surface actually paints, which is the
 * rail, so a docked window keeps its grab edge on screen with its body still
 * unfolded.
 */
export function clampRect(rect: Rect, viewport: Viewport, minimized = false): Rect {
  const width = between(rect.width, OVERLAY_SURFACE_MIN.width, viewport.width)
  const height = between(rect.height, OVERLAY_SURFACE_MIN.height, viewport.height)
  const visible = minimized ? Math.min(OVERLAY_RAIL_HEIGHT, height) : height
  return {
    x: between(rect.x, 0, viewport.width - width),
    y: between(rect.y, 0, viewport.height - visible),
    width,
    height,
  }
}

/**
 * Where a surface lands: `OVERLAY_EDGE` below the top of the window and centred
 * horizontally, then `OVERLAY_CASCADE` per surface already in the stack. The top
 * anchor is a decision: a widget that opened in the middle would cover the composer,
 * which is the one thing this surface may not do to the page behind it.
 */
function placedAbove(stack: OverlayStack, size: Size, viewport: Viewport): Rect {
  const cascade = stack.surfaces.length * OVERLAY_CASCADE
  return clampRect(
    {
      x: Math.round((viewport.width - Math.min(size.width, viewport.width)) / 2) + cascade,
      y: OVERLAY_EDGE + cascade,
      width: size.width,
      height: size.height,
    },
    viewport,
  )
}

/** `created=false` is the desktop twin's answer: the surface was already there. */
export function openSurface(
  stack: OverlayStack,
  spec: SurfaceSpec,
  viewport: Viewport,
  placement?: Rect,
): { stack: OverlayStack; key: string; created: boolean } {
  const key = surfaceKey(spec.pluginId)
  const z = stack.topZ + 1
  const existing = stack.surfaces.some((surface) => surface.key === key)
  /// Reveal, and nothing else. The document on screen was mounted with the
  /// credential it was given; pointing it at a fresher URL would reload the plugin
  /// and throw away its state to buy a nonce it does not need, and the bounds the
  /// user dragged to are theirs.
  if (existing) {
    return {
      stack: {
        ...stack,
        topZ: z,
        surfaces: stack.surfaces.map((surface) =>
          surface.key === key ? { ...surface, z, minimized: false } : surface,
        ),
      },
      key,
      created: false,
    }
  }
  const surface: OverlaySurface = {
    ...spec,
    key,
    bounds: placement
      ? clampRect(placement, viewport)
      : placedAbove(stack, { width: spec.width, height: spec.height }, viewport),
    z,
    minimized: false,
  }
  return {
    stack: { ...stack, topZ: z, surfaces: [...stack.surfaces, surface] },
    key,
    created: true,
  }
}

const mapped = (
  stack: OverlayStack,
  key: string,
  change: (surface: OverlaySurface) => OverlaySurface,
): OverlayStack => {
  if (!stack.surfaces.some((surface) => surface.key === key)) return stack
  return {
    ...stack,
    surfaces: stack.surfaces.map((surface) => (surface.key === key ? change(surface) : surface)),
  }
}

/**
 * Point a standing frame at a new mount URL. Placement stays where the user
 * left it. A second open does not call this: the reveal path keeps the URL the
 * frame already loaded. This runs when that credential has died and the frame
 * has to load a fresh one.
 */
export function retargetSurface(stack: OverlayStack, pluginId: string, url: string): OverlayStack {
  const key = surfaceKey(pluginId)
  const current = stack.surfaces.find((surface) => surface.key === key)
  if (!current || current.url === url) return stack
  return mapped(stack, key, (surface) => ({ ...surface, url }))
}

export function closeSurface(stack: OverlayStack, key: string): OverlayStack {
  if (!stack.surfaces.some((surface) => surface.key === key)) return stack
  return { ...stack, surfaces: stack.surfaces.filter((surface) => surface.key !== key) }
}

/** Raise to the top. Already top, or absent: the same stack object back, so a
 *  re-render that reports focus cannot reshuffle what the user arranged. */
export function focusSurface(stack: OverlayStack, key: string): OverlayStack {
  const top = topSurface(stack)
  if (!stack.surfaces.some((surface) => surface.key === key) || top?.key === key) return stack
  const z = stack.topZ + 1
  return { ...mapped(stack, key, (surface) => ({ ...surface, z })), topZ: z }
}

export const minimizeSurface = (stack: OverlayStack, key: string): OverlayStack =>
  mapped(stack, key, (surface) => ({ ...surface, minimized: true }))

/** The restore is the raise *and* the re-clamp, so it takes a z step of its own:
 *  a surface restored into a window that shrank comes back on top and inside. */
export function restoreSurface(stack: OverlayStack, key: string, viewport: Viewport): OverlayStack {
  if (!stack.surfaces.some((surface) => surface.key === key)) return stack
  const z = stack.topZ + 1
  return {
    ...mapped(stack, key, (surface) => ({
      ...surface,
      minimized: false,
      z,
      bounds: clampRect(surface.bounds, viewport),
    })),
    topZ: z,
  }
}

export const moveSurface = (
  stack: OverlayStack,
  key: string,
  to: { x: number; y: number },
  viewport: Viewport,
): OverlayStack =>
  mapped(stack, key, (surface) => ({
    ...surface,
    bounds: clampRect({ ...surface.bounds, x: to.x, y: to.y }, viewport, surface.minimized),
  }))

export const resizeSurface = (
  stack: OverlayStack,
  key: string,
  size: Size,
  viewport: Viewport,
): OverlayStack =>
  mapped(stack, key, (surface) => ({
    ...surface,
    bounds: clampRect({ ...surface.bounds, ...size }, viewport, surface.minimized),
  }))

/** Keys bottom-up: the render order and the tab order of the rails. */
export const stackOrder = (stack: OverlayStack): string[] =>
  [...stack.surfaces].sort((a, b) => a.z - b.z).map((surface) => surface.key)

export function topSurface(stack: OverlayStack): OverlaySurface | null {
  let top: OverlaySurface | null = null
  for (const surface of stack.surfaces) if (!top || surface.z > top.z) top = surface
  return top
}

export const findSurface = (stack: OverlayStack, key: string): OverlaySurface | undefined =>
  stack.surfaces.find((surface) => surface.key === key)
