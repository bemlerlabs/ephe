/**
 * Where a plugin surface renders, out of the one field the manifest owns.
 *
 * `components.ui.type` is the placement declaration (`core/plugin_ui_capabilities.py`
 * `UI_TYPES`), and it is the only one: a bundle does not name a slot, a position or a
 * DOM node. The shell owns every placement below, and asks this module which of them
 * the declared type gets on the platform it is running on. Both product surfaces read
 * the same answer — the desktop half opens its own window or paints the overlay stack,
 * the browser half has only the stack — so the two cannot disagree about one bundle.
 *
 * `canvas-overlay` is the type that used to disagree: it floated in a browser tab and
 * was refused by the desktop shell. It is a frame on both halves now. `dock-panel` is
 * the type the shell cannot host yet, and it is a coded refusal rather than a frame:
 * the silent downgrade to a floating window is the defect this rule removes. A fallback
 * stays loud (the owner rule `pluginDisplay.ts` states), so the refusal names the code a
 * caller branches on and the move the author still has.
 *
 * What a placement does not do is grant anything. The mount URL, the nonce, the
 * sandbox and the capability list are the ones `server/routes/plugin_ui.py` and
 * `server/plugin_surface_policy.py` already decide, and a type cannot widen them.
 */

/** The closed placement vocabulary of a version 2 manifest. */
export type SurfaceType = 'floating-window' | 'dock-panel' | 'canvas-overlay'

/** Which half is asking. The desktop shell is the only one with native windows. */
export type SurfacePlatform = { isDesktop: boolean }

/** The codes a refused placement answers with, in the `reason_code` spelling the
 *  refusal envelopes use. */
export type SurfaceRefusalCode = 'surface_dock_panel_unavailable' | 'surface_type_unknown'

/** What a refusal carries: the code a caller branches on, and the move it names. */
export type SurfaceRefusal = {
  reason_code: SurfaceRefusalCode
  next: string
}

/** The placement a surface gets, or the refusal that keeps it off screen. */
export type SurfaceResolution =
  | { kind: 'native'; refusal: null }
  | { kind: 'overlay'; refusal: null }
  | { kind: 'canvas-overlay'; refusal: null }
  | { kind: 'refused'; refusal: SurfaceRefusal }

/** The two types a bundle can declare while the docked region is still unbuilt. */
const DECLARABLE = 'floating-window or canvas-overlay'

function dockRefusal(): SurfaceRefusal {
  return {
    reason_code: 'surface_dock_panel_unavailable',
    next: `declare components.ui.type as ${DECLARABLE} until the docked region exists`,
  }
}

function unknownRefusal(): SurfaceRefusal {
  return {
    reason_code: 'surface_type_unknown',
    next: 'declare components.ui.type as floating-window, canvas-overlay or dock-panel',
  }
}

/**
 * `components.ui.type` on this platform.
 *
 * A `floating-window` takes the desktop's own window where there is one and the
 * overlay stack in a tab. A `canvas-overlay` takes the overlay stack on both, because
 * a canvas is a frame on either half. A `dock-panel` is refused until the shell owns a
 * docked region, and a type outside the vocabulary is refused the same way — a
 * descriptor a manifest validator never saw is still not a surface to guess at.
 */
export function resolveSurfacePlacement(
  type: string,
  platform: SurfacePlatform,
): SurfaceResolution {
  if (type === 'canvas-overlay') return { kind: 'canvas-overlay', refusal: null }
  if (type === 'floating-window') {
    return { kind: platform.isDesktop ? 'native' : 'overlay', refusal: null }
  }
  if (type === 'dock-panel') return { kind: 'refused', refusal: dockRefusal() }
  return { kind: 'refused', refusal: unknownRefusal() }
}
