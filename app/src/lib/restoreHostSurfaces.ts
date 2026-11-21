/**
 * Put open host records back on screen after a restart.
 *
 * Each record names the slot and the box. The mount URL is minted again,
 * because the credential from the previous process is gone. A record written
 * for the shell's own window has nothing to restore in a tab; every webview
 * placement (`overlay`, `canvas-overlay`, `dock`) restores on both halves, so a
 * canvas-overlay saved on the desktop comes back as the frame it was and a
 * docked panel comes back in the dock.
 *
 * The dock stands one panel at a time. A state file written before a crash can
 * still hold two open dock records; the last one written wins and the older one
 * is not re-opened, because re-opening it would displace the newest panel the
 * user actually had. Every live collision is closed loudly in
 * `pluginDisplay.openInDock`; this is only the recovery after an unclean stop.
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
  // Object insertion order is the write order here; the last open dock record is the
  // panel that was on screen when the previous process stopped.
  const newestDock = Object.entries(hosts)
    .filter(([, host]) => host.open && host.slot === 'dock')
    .at(-1)?.[0]
  for (const [pluginId, host] of Object.entries(hosts)) {
    if (!host.open) continue
    if (host.slot === 'native' && !desktop) continue
    if (host.slot === 'dock' && pluginId !== newestDock) continue
    const descriptor = descriptors.get(pluginId)
    if (!descriptor) continue
    await showPluginSurface({ pluginId, descriptor, host }, t)
  }
}
