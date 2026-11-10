/**
 * W1-3: the native plugin window.
 *
 * A plugin surface is one document served by the product server at
 * `/api/plugins/ui/<id>/<nonce>/` (#42) and, on the desktop, a window of its own
 * label (`ephe-plugin-<id>`, src-tauri/src/plugin_window.rs). The label is the
 * boundary: that window answers to `capabilities/plugin-window.json`, which grants
 * it nothing at all — its permission list is empty.
 *
 * The descriptor is `ui_descriptor()` as the API returns it — already defaulted and
 * flattened, with snake_case keys — and the shell decides the window shape from it.
 * The shell call `plugin_window_open` takes that descriptor and reports the window it
 * built, so a surface can say what it actually got: a transparent widget can be told
 * it landed as a decorated one.
 *
 * In a browser tab there is no shell, so `canOpenNativeSurface` is false and the
 * overlay dock (#44, `components/shell/OverlayHost.tsx`) is the surface that shows
 * the same plugin. Which of the two a call is answered with is W1-5's decision
 * (`pluginDisplay.ts`, #20); this file holds only the desktop commands and the URL
 * both halves mount. Both halves take the same URL: `mintSurfaceCredential()` buys
 * the per-mount nonce the route asks for and `surfaceMountUrl()` puts it where a
 * frame can carry it — in the path, because a frame sends no header for the
 * document it loads or for the files that document derives.
 */
import { BASE_URL, request } from './api/http'
import { bridge } from './openExternal'

export type SurfaceSlot = 'overlay' | 'native' | 'side-panel'

export type SurfaceDescriptor = {
  type: string
  title?: string
  width?: number
  height?: number
  transparent?: boolean
  /**
   * Above every other window, which is a window-server ask. A browser tab owns no
   * screen area outside its own page, so the overlay half has nothing to put the flag
   * on: `pluginDisplay.ts` keeps it out of the mount and reports the flag in `unmet`.
   */
  always_on_top?: boolean
  /**
   * Where the surface renders: overlay (browser tab), native (desktop window), or
   * side-panel (docked sidebar). The manifest declares the slot; the host honors it.
   * When absent, the runtime picks native on desktop, overlay in the browser.
   */
  slot?: SurfaceSlot
}

export type SurfaceInfo = {
  label: string
  width: number
  height: number
  transparent: boolean
  decorations: boolean
  alwaysOnTop: boolean
  created: boolean
  note: string
}

export type SurfaceBounds = { x: number; y: number; width: number; height: number }

/** Only the desktop has a native window to hand a surface. */
export const canOpenNativeSurface = (): boolean => bridge() !== null

/**
 * The slot a surface renders in: the manifest's declaration wins, or the runtime
 * default when the manifest says nothing. A plugin that declares `side-panel` on
 * desktop gets the side panel, not a native window — the declaration is the contract.
 */
export function resolveSurfaceSlot(
  declared: SurfaceSlot | undefined,
  runtime: { isDesktop: boolean },
): SurfaceSlot {
  if (declared !== undefined) return declared
  return runtime.isDesktop ? 'native' : 'overlay'
}

/**
 * The label the shell gives this plugin's window: `PLUGIN_LABEL_PREFIX` plus the id,
 * as `src-tauri/src/plugin_window_options.rs` builds it. The same string comes back in
 * `SurfaceInfo.label` and in the `plugin-window:closed` event, so a caller that holds
 * it can match both without reading the prefix scheme a second time.
 */
export const nativeSurfaceLabel = (pluginId: string): string => `ephe-plugin-${pluginId}`

export async function openPluginSurface(
  pluginId: string,
  url: string,
  descriptor: SurfaceDescriptor,
): Promise<SurfaceInfo | null> {
  const core = bridge()?.core
  if (!core) return null
  return (await core('plugin_window_open', { pluginId, url, descriptor })) as SurfaceInfo
}

export async function closePluginSurface(handle: string): Promise<boolean> {
  const core = bridge()?.core
  if (!core) return false
  return (await core('plugin_window_close', { handle })) as boolean
}

export async function setPluginSurfaceBounds(handle: string, bounds: SurfaceBounds): Promise<void> {
  await bridge()?.core('plugin_window_bounds', { handle, bounds })
}

export type SurfaceEvent = { kind: 'opened'; info: SurfaceInfo } | { kind: 'closed'; label: string }

/** The shell reports every surface it opened or closed back to the main window. */
export function listenNativeSurfaces(onEvent: (event: SurfaceEvent) => void): () => void {
  const listen = bridge()?.listen
  if (!listen) return () => {}
  let dead = false
  const unlisten: (() => void)[] = []
  const attach = (name: string, map: (payload: unknown) => SurfaceEvent) => {
    void listen(name, (event) => {
      if (!dead) onEvent(map(event.payload))
    })
      .then((fn) => (dead ? fn() : unlisten.push(fn)))
      .catch(() => {
        /* without an event channel the surface list simply stays where it was */
      })
  }
  attach('plugin-window:opened', (payload) => ({
    kind: 'opened',
    info: payload as SurfaceInfo,
  }))
  attach('plugin-window:closed', (payload) => ({
    kind: 'closed',
    label: String(payload ?? ''),
  }))
  return () => {
    dead = true
    unlisten.forEach((fn) => fn())
  }
}

/**
 * The mint: `POST /api/plugins/{plugin_id}/surface-token` (#42). The route sits
 * behind the LAN check and the same-origin XHR marker, so it is issued to this
 * authenticated fetch and to nothing else, and the value is held in the server
 * process — a restart takes every mount credential with it.
 *
 * The credential lives for `SURFACE_NONCE_TTL_SECONDS` (300 s). While a surface
 * stands, the parent asks this same route to keep that value alive. A fetch of
 * the document does not move the clock. A dead value answers 401, and the parent
 * then mounts a fresh one, which reloads the frame.
 */
export async function mintSurfaceCredential(pluginId: string): Promise<string> {
  const minted = await request<{ plugin: string; surface: string; expires_in: number }>(
    `/api/plugins/${encodeURIComponent(pluginId)}/surface-token`,
    { method: 'POST' },
  )
  return minted.surface
}

/** Keep the credential the frame already holds. A dead value rejects. */
export async function renewSurfaceCredential(pluginId: string, nonce: string): Promise<string> {
  const minted = await request<{ plugin: string; surface: string; expires_in: number }>(
    `/api/plugins/${encodeURIComponent(pluginId)}/surface-token`,
    { method: 'POST', body: JSON.stringify({ surface: nonce }) },
  )
  return minted.surface
}

/**
 * The URL a frame mounts: the directory shape, with the nonce as one path segment
 * so every file the document derives inherits it. `base` defaults to the base the
 * app resolves for its own platform (`''` on the product server, the loopback
 * address in the shell); the LAN token never enters this string.
 */
export function surfaceMountUrl(pluginId: string, nonce: string, base = BASE_URL): string {
  return `${base}/api/plugins/ui/${encodeURIComponent(pluginId)}/${encodeURIComponent(nonce)}/`
}
