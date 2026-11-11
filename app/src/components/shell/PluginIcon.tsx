/**
 * Ephe — plugin icon tile.
 *
 * An img element cannot send a header. Off loopback the icon route answers
 * 401 unless X-Auth-Token is present, and that token stays out of the URL.
 * The tile fetches the bytes with the same header the API client uses and
 * paints a blob. A missed fetch falls back to the lettermark.
 */
import { useEffect, useState } from 'react'
import { BASE_URL, LAN_TOKEN } from '@/lib/api'
import slugAngle from './slugAngle'

const loads = new Map<string, Promise<string | null>>()

/**
 * One fetch per plugin id, and the refusal is remembered with it. The icon route
 * 404s for every manifest that names no icon; deleting the failed promise made
 * each visit ask again (four 404s on every settings open, QA-E2E F5).
 */
function loadPluginIcon(pluginId: string): Promise<string | null> {
  const hit = loads.get(pluginId)
  if (hit) return hit
  const headers: Record<string, string> = { 'X-Requested-With': 'XMLHttpRequest' }
  if (LAN_TOKEN) headers['X-Auth-Token'] = LAN_TOKEN
  const pending = fetch(`${BASE_URL}/api/plugins/icon/${encodeURIComponent(pluginId)}`, {
    headers,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(String(response.status))
      return URL.createObjectURL(await response.blob())
    })
    .catch(() => null)
  loads.set(pluginId, pending)
  return pending
}

function Lettermark({
  pluginId,
  initial,
  edge,
}: {
  pluginId: string
  initial: string
  edge: { width: number; height: number } | undefined
}) {
  return (
    <span
      data-testid={`plugin-icon-${pluginId}`}
      className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-brand/20 text-ui-base font-semibold text-foreground/90"
      style={{
        ...edge,
        background: `linear-gradient(${slugAngle(pluginId)}deg, color-mix(in oklab, var(--color-brand) 22%, var(--color-canvas)), var(--color-canvas))`,
      }}
    >
      {initial}
    </span>
  )
}

export default function PluginIcon({
  pluginId,
  name,
  size,
  hasIcon,
}: {
  pluginId: string
  name: string
  /** Rendered edge in px; the default keeps the 44 px tile of the installed list. */
  size?: number
  /**
   * `false` from the plugin payload means the manifest names no icon, and the
   * route would answer 404. `undefined` keeps the old request for callers that
   * predate the field.
   */
  hasIcon?: boolean
}) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const initial = (name || pluginId || '?').trim().charAt(0).toUpperCase()
  const edge = size ? { width: size, height: size } : undefined

  useEffect(() => {
    let live = true
    setSrc(null)
    setFailed(false)
    if (hasIcon === false) return
    loadPluginIcon(pluginId).then(
      (url) => {
        if (!live) return
        if (url === null) setFailed(true)
        else setSrc(url)
      },
      () => {
        if (live) setFailed(true)
      },
    )
    return () => {
      live = false
    }
  }, [pluginId, hasIcon])

  if (failed || !src) {
    return <Lettermark pluginId={pluginId} initial={initial} edge={edge} />
  }
  return (
    <img
      data-testid={`plugin-icon-${pluginId}`}
      src={src}
      alt=""
      aria-hidden="true"
      onError={() => setFailed(true)}
      className="h-11 w-11 shrink-0 rounded-xl"
      style={edge}
    />
  )
}
