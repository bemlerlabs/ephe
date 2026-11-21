/**
 * Where a plugin surface renders, out of the one field the manifest owns.
 *
 * `components.ui.type` is the placement declaration (`core/plugin_ui_capabilities.py`
 * `UI_TYPES`), and it is the only one: a bundle does not name a slot, a position or a
 * DOM node. The shell owns every placement below, and asks this module which of them
 * the declared type gets on the platform it is running on. Both product surfaces read
 * the same answer — the desktop half is the same PWA inside its own window, so a
 * placement the browser hosts is the one the desktop hosts too. Only the native
 * window is desktop-only, and the desktop shell renders the docked region from the
 * same bundle the browser uses (`app/src/components/shell/DockHost.tsx`).
 *
 * `canvas-overlay` is the type that used to disagree: it floated in a browser tab and
 * was refused by the desktop shell. It is a frame on both halves now. `dock-panel`
 * used to be a coded refusal, and is the shell's docked region on both halves: one
 * panel at a time in a fixed column, a bottom sheet behind a toggle on a phone. A
 * type outside the vocabulary is still a refusal rather than a guess, and a fallback
 * stays loud (the owner rule `pluginDisplay.ts` states).
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
 *  refusal envelopes use. A declared type has a placement, so only a descriptor the
 *  manifest validator never saw is left to refuse. */
export type SurfaceRefusalCode = 'surface_type_unknown'

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
  | { kind: 'dock'; refusal: null }
  | { kind: 'refused'; refusal: SurfaceRefusal }

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
 * a canvas is a frame on either half. A `dock-panel` takes the docked region on both,
 * because the desktop paints the same PWA. A type outside the vocabulary is refused:
 * a descriptor a manifest validator never saw is not a surface to guess at.
 */
export function resolveSurfacePlacement(
  type: string,
  platform: SurfacePlatform,
): SurfaceResolution {
  if (type === 'dock-panel') return { kind: 'dock', refusal: null }
  if (type === 'canvas-overlay') return { kind: 'canvas-overlay', refusal: null }
  if (type === 'floating-window') {
    return { kind: platform.isDesktop ? 'native' : 'overlay', refusal: null }
  }
  return { kind: 'refused', refusal: unknownRefusal() }
}
