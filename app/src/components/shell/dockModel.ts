/**
 * The docked plugin surface — one panel at a time, in a region the shell owns.
 *
 * `components.ui.type: "dock-panel"` lands here (resolved by `surfacePlacement.ts`),
 * and nothing about the panel is the bundle's to place: the region, its width, its
 * order and its chrome belong to `DockHost.tsx`. The bundle chooses the content and
 * nothing else, which is why this model carries no geometry.
 *
 * The one rule the model states, because a caller has to act on it: a second dock
 * replaces the first. The displaced panel is returned rather than dropped, so the
 * caller can close its surface loudly — a plugin that vanishes from the dock without
 * a word is the silent fallback the owner rule forbids. Newest wins, one at a time.
 *
 * A phone shows the same panel as a bottom sheet behind a toggle; `collapsed` is that
 * toggle's state and the wide window ignores it (the column is always open there).
 */

/** What opening a dock needs: the mount URL plus the copy the chrome draws. */
export type DockSpec = {
  pluginId: string
  title: string
  url: string
  surfaceType: string
}

/** The panel in the region, and whether the phone-level sheet is folded away. */
export type DockPanel = DockSpec & { collapsed: boolean }

/** The fixed width of the docked column on a wide window. */
export const DOCK_WIDTH = 360

export type DockOpen = {
  panel: DockPanel
  /** The panel this open displaced; null when the same plugin was already docked. */
  replaced: DockPanel | null
  /** False when the same plugin was already in the dock and this open only revealed it. */
  created: boolean
}

/** The handle a caller keeps: stable per plugin, like `overlay:<id>` on the stack. */
export const dockKey = (pluginId: string): string => `dock:${pluginId}`

/**
 * Put one panel in the dock. The same plugin already standing is revealed, not
 * re-mounted: the document keeps the credential it was given and the sheet unfolds.
 * A different plugin displaces the standing one, and the caller learns which.
 */
export function openDocked(current: DockPanel | null, spec: DockSpec): DockOpen {
  if (current && current.pluginId === spec.pluginId) {
    return {
      panel: { ...current, collapsed: false },
      replaced: null,
      created: false,
    }
  }
  return {
    panel: { ...spec, collapsed: false },
    replaced: current,
    created: true,
  }
}

/** Take the named plugin's panel out. An ask for another plugin is a no-op. */
export function closeDocked(current: DockPanel | null, pluginId?: string): DockPanel | null {
  if (!current) return null
  if (pluginId && current.pluginId !== pluginId) return current
  return null
}

/** Replace the mount URL after the standing credential has died. */
export function retargetDocked(
  current: DockPanel | null,
  pluginId: string,
  url: string,
): DockPanel | null {
  if (!current || current.pluginId !== pluginId) return current
  if (current.url === url) return current
  return { ...current, url }
}

/** Fold or unfold the phone sheet. The wide window ignores the flag. */
export function collapseDocked(
  current: DockPanel | null,
  pluginId: string,
  collapsed: boolean,
): DockPanel | null {
  if (!current || current.pluginId !== pluginId) return current
  if (current.collapsed === collapsed) return current
  return { ...current, collapsed }
}
