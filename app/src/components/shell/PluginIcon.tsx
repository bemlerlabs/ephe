/**
 * Ephe — S wave: PluginIcon (extensions v2, E2, out/plan.md [S1]-[S4]).
 *
 * Loads the vendor icon from the plugin directory (/api/plugins/icon/{id}) and on
 * 404/load failure falls back to a deterministic lettermark (first letter on a
 * moss gradient, angle from the slug hash) — the tile stays ordered, never broken.
 */
import { useState } from 'react'
import slugAngle from './slugAngle'

export default function PluginIcon({ pluginId, name }: { pluginId: string; name: string }) {
  const [failed, setFailed] = useState(false)
  const initial = (name || pluginId || '?').trim().charAt(0).toUpperCase()
  const angle = slugAngle(pluginId)

  if (failed) {
    return (
      <span
        data-testid={`plugin-icon-${pluginId}`}
        className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-brand/20 text-ui-base font-semibold text-foreground/90"
        style={{
          background: `linear-gradient(${angle}deg, color-mix(in oklab, var(--color-brand) 22%, var(--color-canvas)), var(--color-canvas))`,
        }}
      >
        {initial}
      </span>
    )
  }
  return (
    <img
      data-testid={`plugin-icon-${pluginId}`}
      src={`/api/plugins/icon/${pluginId}`}
      alt=""
      aria-hidden="true"
      onError={() => setFailed(true)}
      className="h-11 w-11 shrink-0 rounded-xl"
    />
  )
}
