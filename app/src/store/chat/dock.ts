import {
  closeDocked,
  collapseDocked,
  openDocked,
  retargetDocked,
  type DockPanel,
  type DockSpec,
} from '@/components/shell/dockModel'
import type { ChatState, StoreCtx } from './types'

/**
 * The docked plugin surface.
 *
 * The one-panel rule and its displaced answer live in `dockModel.ts`; this slice only
 * routes a call to the model and stores what it returned. It sits beside the overlay
 * slice because both are transient shell state the display module reads, and because
 * a surface that opens in one and closes in the other must be one stored fact.
 */
export function makeDockActions(ctx: StoreCtx): Partial<ChatState> {
  const { set, get } = ctx
  const dock = (): DockPanel | null => get().dock
  return {
    openDock: (spec: DockSpec) => {
      const opened = openDocked(dock(), spec)
      set({ dock: opened.panel })
      return { replaced: opened.replaced, created: opened.created }
    },
    closeDock: (pluginId?: string) => set({ dock: closeDocked(dock(), pluginId) }),
    retargetDock: (pluginId: string, url: string) =>
      set({ dock: retargetDocked(dock(), pluginId, url) }),
    collapseDock: (pluginId: string, collapsed: boolean) =>
      set({ dock: collapseDocked(dock(), pluginId, collapsed) }),
  }
}
