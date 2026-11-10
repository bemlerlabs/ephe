import {
  closeSurface,
  focusSurface,
  minimizeSurface,
  moveSurface,
  type OverlayStack,
  type Rect,
  type Size,
  type SurfaceSpec,
  openSurface,
  retargetSurface,
  resizeSurface,
  restoreSurface,
  type Viewport,
} from '@/components/shell/overlayModel'
import type { ChatState, StoreCtx } from './types'

/**
 * W1-4 — the plugin overlay stack.
 *
 * The stack itself is `overlayModel`'s business; this slice only routes a call to
 * the reducer and stores the answer. Two reasons it lives in the shell's store and
 * nowhere else: the dock that paints it and the caller that opens a surface have to
 * read one object, and the desktop twin keeps the same rule (one window per plugin,
 * raised by a second open) behind a window label the shell owns.
 *
 * The live stack stays in this store. The host record written beside the mount
 * is the slot, the box, and whether the surface is open. The page's scroll and
 * form stay in the frame. A drag is still not a session edit, so no path here
 * reaches `persistActive`.
 */
export function makeOverlayActions(ctx: StoreCtx): Partial<ChatState> {
  const { set, get } = ctx
  const stack = (): OverlayStack => get().overlay
  const write = (next: OverlayStack) => set({ overlay: next })
  return {
    openOverlay: (spec: SurfaceSpec, viewport: Viewport, placement?: Rect) => {
      const opened = openSurface(stack(), spec, viewport, placement)
      write(opened.stack)
      return { key: opened.key, created: opened.created }
    },
    closeOverlay: (key: string) => write(closeSurface(stack(), key)),
    retargetOverlay: (pluginId: string, url: string) =>
      write(retargetSurface(stack(), pluginId, url)),
    focusOverlay: (key: string) => write(focusSurface(stack(), key)),
    minimizeOverlay: (key: string) => write(minimizeSurface(stack(), key)),
    restoreOverlay: (key: string, viewport: Viewport) =>
      write(restoreSurface(stack(), key, viewport)),
    moveOverlay: (key: string, to: { x: number; y: number }, viewport: Viewport) =>
      write(moveSurface(stack(), key, to, viewport)),
    resizeOverlay: (key: string, size: Size, viewport: Viewport) =>
      write(resizeSurface(stack(), key, size, viewport)),
  }
}
