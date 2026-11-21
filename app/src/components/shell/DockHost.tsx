/**
 * The docked plugin region — the shell's own column for a `dock-panel` surface.
 *
 * A bundle declaring `components.ui.type: "dock-panel"` gets this region and nothing
 * about its geometry: the shell owns the width, the order and the chrome, and a phone
 * shows the same panel as a bottom sheet behind a toggle. The frame is the same
 * sandboxed, nonce-mounted document the overlay half paints (`OverlayHost.tsx`): the
 * region changes where it renders, never what it may do.
 *
 * The panel is transient store state (`dockModel.ts`), so a close here goes through
 * `hidePluginSurface` exactly as the store row's button does — one close path, one
 * host record, one credential release. The region paints nothing while no plugin asks
 * for it, which is why the shell can mount it unconditionally.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, PanelRight, X } from 'lucide-react'
import { useChatStore } from '@/store'
import { attachPluginClient } from '@/lib/pluginClientHost'
import { hidePluginSurface } from '@/lib/pluginDisplay'
import './DockHost.css'

/** The embedder's copy of `server/plugin_surface_policy.py`'s isolation directive.
 *  Same value and same reason as `OverlayHost.tsx`: no same-origin authority. */
const SURFACE_SANDBOX = 'allow-scripts allow-popups'

export default function DockHost() {
  const panel = useChatStore((s) => s.dock)
  const collapseDock = useChatStore((s) => s.collapseDock)
  const { t } = useTranslation()
  const frame = useRef<HTMLIFrameElement>(null)
  const pluginId = panel?.pluginId ?? ''

  useEffect(() => {
    const node = frame.current
    if (!node || !pluginId) return
    return attachPluginClient(node, pluginId)
  }, [pluginId])

  if (!panel) return null
  const name = panel.title || panel.pluginId
  const regionId = `plugin-dock-${panel.pluginId}`

  return (
    <>
      {panel.collapsed && (
        <button
          type="button"
          className="dock-toggle focus-ring"
          data-testid="dock-toggle"
          aria-expanded={false}
          aria-controls={regionId}
          aria-label={t('surface.dockExpand')}
          onClick={() => collapseDock(panel.pluginId, false)}
        >
          <PanelRight className="h-4 w-4" aria-hidden="true" />
          <span className="dock-toggle-name">{name}</span>
        </button>
      )}
      <aside
        id={regionId}
        className="dock-host"
        data-testid="dock-host"
        data-collapsed={panel.collapsed}
        role="complementary"
        aria-label={t('surface.dockRegionAria')}
      >
        <div className="dock-chrome">
          <h2 className="dock-title" data-testid="dock-title">
            {name}
          </h2>
          <button
            type="button"
            className="dock-control dock-collapse focus-ring"
            data-testid="dock-collapse"
            aria-expanded={!panel.collapsed}
            aria-controls={regionId}
            aria-label={t('surface.dockCollapse')}
            onClick={() => collapseDock(panel.pluginId, true)}
          >
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="dock-control focus-ring"
            data-testid="dock-close"
            aria-label={t('a11y.close')}
            onClick={() => void hidePluginSurface(panel.pluginId, t)}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="dock-body">
          <iframe
            ref={frame}
            data-testid="dock-frame"
            className="dock-frame"
            title={name}
            src={panel.url}
            sandbox={SURFACE_SANDBOX}
            allow=""
            referrerPolicy="no-referrer"
          />
        </div>
      </aside>
    </>
  )
}
