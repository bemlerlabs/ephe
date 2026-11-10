/**
 * The host half of a plugin surface.
 *
 * Slot, box, and whether the window is open. The page inside the frame keeps
 * scroll and form values on its own storage route, and this record has no
 * field for them. `placed` is false while the shell has not reported a
 * position; a restore then leaves the shell's own placement alone.
 */
import { request } from './api/http'
import type { SurfaceSlot } from './pluginSurface'

export type { SurfaceSlot }

export type HostSurface = {
  slot: SurfaceSlot
  x: number
  y: number
  width: number
  height: number
  open: boolean
  minimized: boolean
  placed: boolean
}

const FIELDS = ['slot', 'x', 'y', 'width', 'height', 'open', 'minimized', 'placed'] as const

const remembered = new Map<string, HostSurface>()

export function hostRecord(input: HostSurface): HostSurface {
  return {
    slot: input.slot,
    x: Math.round(input.x),
    y: Math.round(input.y),
    width: Math.round(input.width),
    height: Math.round(input.height),
    open: input.open,
    minimized: input.minimized,
    placed: input.placed,
  }
}

/** The keys a host record is allowed to carry. A test pins the set. */
export function hostRecordKeys(record: HostSurface): string[] {
  return Object.keys(hostRecord(record)).filter((key) =>
    (FIELDS as readonly string[]).includes(key),
  )
}

export function lastHost(pluginId: string): HostSurface | undefined {
  const found = remembered.get(pluginId)
  return found ? { ...found } : undefined
}

export async function saveHostSurface(pluginId: string, record: HostSurface): Promise<void> {
  const body = hostRecord(record)
  remembered.set(pluginId, body)
  await request(`/api/plugins/${encodeURIComponent(pluginId)}/surface-host`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export async function loadHostSurfaces(): Promise<Record<string, HostSurface>> {
  const view = await request<{ surfaces?: Record<string, HostSurface> }>(
    '/api/plugins/surface-hosts',
  )
  return view.surfaces ?? {}
}
