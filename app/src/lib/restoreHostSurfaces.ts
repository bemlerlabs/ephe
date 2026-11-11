/**
 * Put open host records back on screen after a restart.
 *
 * Each record names the slot and the box. The mount URL is minted again,
 * because the credential from the previous process is gone. A record written
 * for the shell's own window has nothing to restore in a tab; every webview
 * placement (`overlay`, `canvas-overlay`) restores on both halves, so a
 * canvas-overlay saved on the desktop comes back as the frame it was.
 */
import { request } from './api/http'
import { showPluginSurface, type Translate } from './pluginDisplay'
import { canOpenNativeSurface, type SurfaceDescriptor } from './pluginSurface'
import { loadHostSurfaces } from './surfaceHost'

type Row = { name?: string; surface?: SurfaceDescriptor & { entry?: string } }
type View = { public?: Row[]; personal?: Row[] }

let started = false

/** Tests call this so a later case can restore again. */
export function resetHostRestore(): void {
  started = false
}

export async function restoreHostSurfaces(t: Translate): Promise<void> {
  if (started) return
  started = true
  const desktop = canOpenNativeSurface()
  const [hosts, view] = await Promise.all([loadHostSurfaces(), request<View>('/api/plugins')])
  const descriptors = new Map<string, SurfaceDescriptor>()
  for (const row of [...(view.public ?? []), ...(view.personal ?? [])]) {
    if (row.name && row.surface?.entry) descriptors.set(row.name, row.surface)
  }
  for (const [pluginId, host] of Object.entries(hosts)) {
    if (!host.open) continue
    if (host.slot === 'native' && !desktop) continue
    const descriptor = descriptors.get(pluginId)
    if (!descriptor) continue
    await showPluginSurface({ pluginId, descriptor, host }, t)
  }
}
