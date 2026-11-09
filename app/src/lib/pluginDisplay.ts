/**
 * W1-5 — one place decides where a plugin surface shows.
 *
 * The desktop half (#43, `pluginSurface.ts`) hands the plugin document to a window of
 * its own label; the browser half (#44, `components/shell/OverlayHost.tsx`) paints the
 * same document in a frame the shell draws. A caller — today the plugin store's switch
 * row, tomorrow the creator card that will follow it — asks this module for the surface
 * and is answered with the one its platform has. "Am I in the shell?" is asked here and
 * nowhere else, and it is asked with the signal `pluginSurface.ts` already reads through
 * the bridge, so no fourth platform detector joins the three the tree carries.
 *
 * The rule that shapes every path below is the owner's: a fallback is loud. A surface
 * asked for on the desktop and refused there stays refused — the user is told, in the
 * words that layer already uses for that refusal, and no overlay is opened behind its
 * back. The browser half answers the same way when it cannot mount the document. A
 * plugin that quietly lands on the other surface is the defect #20 was opened for, and
 * a caller that never hears about it cannot be blamed for a surface it believes it
 * showed.
 *
 * What the two sides cannot deliver is stated where the decision is made.
 * `always_on_top` is a window-server ask, and a tab owns no screen area outside its own
 * page, so the browser path lists the flag in `unmet` and says the difference out loud.
 * The desktop path carries `SurfaceInfo.note`, which is where the shell writes that a
 * transparent widget came back decorated.
 *
 * Held open, unmeasured: the desktop answer to "is this surface standing?" reads the
 * ledger below, which the shell fills through `plugin-window:opened` and
 * `plugin-window:closed`. Both of those ride `emit_to` on the workbench label, and the
 * command result is discarded on the Rust side, so a report that never arrives leaves
 * this ledger holding a surface the user already closed from its own title bar. Whether
 * one arrives with a browser pane attached is open in both directions: #69 measured
 * `get_webview_window("main")` answering None in that state, while `emit_to` matches
 * registered listeners by label in the engine's event manager. Nothing here retries
 * around it, and the surface commands themselves only ever look up their own
 * `ephe-plugin-<id>` label. #69 owns the repair.
 */
import { useChatStore } from '@/store'
import type { Rect, SurfaceSpec, Viewport } from '@/components/shell/overlayModel'
import { lastHost, saveHostSurface, type HostSurface } from '@/lib/surfaceHost'
import { ApiError } from './api/http'
import { toastBus } from './toast'
import {
  canOpenNativeSurface,
  closePluginSurface,
  listenNativeSurfaces,
  mintSurfaceCredential,
  nativeSurfaceLabel,
  openPluginSurface,
  renewSurfaceCredential,
  setPluginSurfaceBounds,
  surfaceMountUrl,
  type SurfaceDescriptor,
  type SurfaceInfo,
} from './pluginSurface'

export { canOpenNativeSurface }

/** The copy lookup a caller hands in: the same shape `backendParity.ts` uses. */
export type Translate = (key: string, options?: Record<string, unknown>) => string

/** Which surface this platform answered with. */
export type SurfaceSide = 'native' | 'overlay'

export type SurfaceRequest = {
  pluginId: string
  /** `ui_descriptor()` as the API returns it: defaulted, flattened, snake_case. */
  descriptor: SurfaceDescriptor
  /** A mount URL the caller already holds. Without one, the credential is minted here. */
  url?: string
  /** The box the overlay half places itself in; the desktop half sizes its own window. */
  viewport?: Viewport
  /** A host record from the last session. The page's own state is not in it. */
  host?: HostSurface
}

export type SurfaceOutcome = {
  opened: boolean
  /** The side that shows the surface; null while nothing is standing. */
  side: SurfaceSide | null
  /** False when the surface already stood and this call only revealed it — the same
   * answer on both halves (`SurfaceInfo.created`, the store's `openOverlay`). */
  created: boolean
  /** What a later close hands back: the window label on the desktop, the store key in
   * the browser. Empty when nothing is standing. */
  handle: string
  /** Descriptor flags this side has no equivalent for. */
  unmet: string[]
  /** The shell's own sentence about a window that came back different from the ask. */
  note: string
  /** The copy key the refusal was read out under; empty when the surface is on screen. */
  message: string
}

/** The size `core/plugin_ui_capabilities.py` falls back to for a descriptor that names
 *  none, the number `plugin_window_options.rs` repeats for its window. The browser half
 *  needs it to size the box the desktop half would have built. */
const DEFAULT_SURFACE_SIZE = { width: 480, height: 320 }

/** Labels the shell opened and has not reported closed. Keyed by the label the events
 *  carry, so an open from the command and a report from the shell land in one entry. */
const nativeLedger = new Map<string, SurfaceInfo>()
let nativeEvents: (() => void) | null = null

/** The shell reports every surface it opened or closed to the workbench. One listen,
 *  installed on the first question anyone asks, and only where a bridge answers it. */
function watchNativeSurfaces(): void {
  if (nativeEvents || !canOpenNativeSurface()) return
  nativeEvents = listenNativeSurfaces((event) => {
    if (event.kind === 'closed') {
      nativeLedger.delete(event.label)
      const pluginId = event.label.startsWith('ephe-plugin-')
        ? event.label.slice('ephe-plugin-'.length)
        : ''
      if (pluginId) {
        releaseSurfaceCredential(pluginId)
        const prior = lastHost(pluginId)
        if (prior) void saveHostSurface(pluginId, { ...prior, open: false }).catch(() => {})
      }
    } else nativeLedger.set(event.info.label, event.info)
  })
}

const overlaySurface = (pluginId: string) =>
  useChatStore.getState().overlay.surfaces.find((surface) => surface.pluginId === pluginId)

/** The desktop half's answer, read from the ledger the shell fills. */
export const isNativeSurfaceOpen = (pluginId: string): boolean =>
  nativeLedger.has(nativeSurfaceLabel(pluginId))

/** Is this plugin's surface on screen — on whichever side this platform has one. */
export function isPluginSurfaceOpen(pluginId: string): boolean {
  watchNativeSurfaces()
  return isNativeSurfaceOpen(pluginId) || overlaySurface(pluginId) !== undefined
}

/**
 * The sentence a refusal carries.
 *
 * `plugin_window.rs` rejects with a curated string and nothing else, and the API layer
 * hands back an `ApiError` whose message is already the reader's own language. A cause
 * that says nothing of itself is answered with an empty detail: the headline still
 * names what stayed closed, and a runtime's own words never become the product's.
 */
function refusalText(cause: unknown): string {
  if (typeof cause === 'string') return cause
  if (cause instanceof Error && cause.message) return cause.message
  return ''
}

function reportFailure(t: Translate, key: string, detail: string): SurfaceOutcome {
  toastBus.error(t(key), detail || undefined)
  return {
    opened: false,
    side: null,
    created: false,
    handle: '',
    unmet: [],
    note: '',
    message: key,
  }
}

const viewportNow = (): Viewport => ({ width: window.innerWidth, height: window.innerHeight })

function overlaySpec(pluginId: string, descriptor: SurfaceDescriptor, url: string): SurfaceSpec {
  return {
    pluginId,
    title: descriptor.title ?? '',
    surfaceType: descriptor.type,
    url,
    width: descriptor.width || DEFAULT_SURFACE_SIZE.width,
    height: descriptor.height || DEFAULT_SURFACE_SIZE.height,
    transparent: descriptor.transparent === true,
  }
}

/**
 * Show this plugin's surface where this platform can show it.
 *
 * The decision is one line long — the bridge is there or it is not — and it is the only
 * place that asks. Both branches report their own failures and return; neither hands the
 * call to the other half.
 */
export async function showPluginSurface(
  request: SurfaceRequest,
  t: Translate,
): Promise<SurfaceOutcome> {
  const { pluginId, descriptor } = request
  watchNativeSurfaces()
  const native = canOpenNativeSurface()

  // A surface that already stands is revealed on both halves. Only the browser half can
  // do it from the URL it already holds: `plugin_window_open` re-points the window at
  // whatever address it is given, so a desktop reveal buys a live credential like any
  // other open. The same reasoning is `overlayModel`'s reveal rule — a mounted document
  // keeps the state its credential bought it.
  const carried = native ? '' : (overlaySurface(pluginId)?.url ?? '')
  let url = request.url ?? carried
  if (!url) {
    try {
      url = surfaceMountUrl(pluginId, await mintSurfaceCredential(pluginId))
    } catch (cause) {
      return reportFailure(t, 'surface.cannotMount', refusalText(cause))
    }
  }

  const outcome = native
    ? await openOnDesktop(pluginId, url, descriptor, t, request.host)
    : openInBrowser(pluginId, descriptor, url, request.viewport ?? viewportNow(), t, request.host)
  if (outcome.opened) {
    holdSurfaceCredential(pluginId, url, descriptor)
    void saveHostSurface(
      pluginId,
      hostAfterOpen(pluginId, native ? 'native' : 'overlay', request.host, descriptor),
    ).catch(() => {})
  }
  return outcome
}

function hostAfterOpen(
  pluginId: string,
  slot: 'native' | 'overlay',
  host: HostSurface | undefined,
  descriptor: SurfaceDescriptor,
): HostSurface {
  const standing = overlaySurface(pluginId)
  if (standing) {
    return {
      slot: 'overlay',
      x: Math.round(standing.bounds.x),
      y: Math.round(standing.bounds.y),
      width: Math.round(standing.bounds.width),
      height: Math.round(standing.bounds.height),
      open: true,
      minimized: standing.minimized,
      placed: true,
    }
  }
  return {
    slot,
    x: host?.x ?? 0,
    y: host?.y ?? 0,
    width: host?.width || descriptor.width || DEFAULT_SURFACE_SIZE.width,
    height: host?.height || descriptor.height || DEFAULT_SURFACE_SIZE.height,
    open: true,
    minimized: false,
    placed: host?.placed === true,
  }
}

async function openOnDesktop(
  pluginId: string,
  url: string,
  descriptor: SurfaceDescriptor,
  t: Translate,
  host?: HostSurface,
): Promise<SurfaceOutcome> {
  let info: SurfaceInfo | null
  try {
    info = await openPluginSurface(pluginId, url, descriptor)
  } catch (cause) {
    return reportFailure(t, 'surface.nativeRefused', refusalText(cause))
  }
  if (!info) {
    // No channel answered. The sentence a caller needs is the one the headline already
    // carries: there was no window, and nothing else was tried.
    return reportFailure(t, 'surface.nativeRefused', '')
  }
  nativeLedger.set(info.label, info)
  if (host?.placed) {
    try {
      await setPluginSurfaceBounds(info.label, {
        x: host.x,
        y: host.y,
        width: host.width,
        height: host.height,
      })
    } catch {
      // The window is up. The saved place did not apply.
    }
  }
  if (info.note) toastBus.info(t('surface.landedDifferently'), info.note)
  return {
    opened: true,
    side: 'native',
    created: info.created,
    handle: info.label,
    unmet: [],
    note: info.note,
    message: '',
  }
}

function openInBrowser(
  pluginId: string,
  descriptor: SurfaceDescriptor,
  url: string,
  viewport: Viewport,
  t: Translate,
  host?: HostSurface,
): SurfaceOutcome {
  const placement: Rect | undefined = host?.placed
    ? { x: host.x, y: host.y, width: host.width, height: host.height }
    : undefined
  const opened = useChatStore
    .getState()
    .openOverlay(overlaySpec(pluginId, descriptor, url), viewport, placement)
  if (host?.minimized && opened.created) {
    useChatStore.getState().minimizeOverlay(opened.key)
  }
  const standing = overlaySurface(pluginId)
  if (!standing) {
    // The dock paints from this store, so a surface the store does not hold is a frame
    // the user will never see. Say it; the desktop has no window to try.
    return reportFailure(t, 'surface.overlayRefused', '')
  }
  const unmet = descriptor.always_on_top ? ['always_on_top'] : []
  if (unmet.length) toastBus.info(t('surface.landedDifferently'), t('surface.notOnTop'))
  return {
    opened: true,
    side: 'overlay',
    created: opened.created,
    handle: opened.key,
    unmet,
    note: '',
    message: '',
  }
}

/**
 * Take this plugin's surface off screen — the same module that mounted it reads the
 * same ledger, so a close and the reopen that follows it travel one path.
 *
 * The answer says whether a standing surface came down. When nothing was standing,
 * the caller learns that too: the row resets its label and the user sees the truth
 * the store holds, a loud no per the rule above.
 */
export async function hidePluginSurface(pluginId: string, t: Translate): Promise<boolean> {
  watchNativeSurfaces()
  const label = nativeSurfaceLabel(pluginId)
  if (canOpenNativeSurface() && nativeLedger.has(label)) {
    let closed = false
    try {
      closed = (await closePluginSurface(label)) === true
    } catch {
      closed = false
    }
    if (closed) {
      nativeLedger.delete(label)
      releaseSurfaceCredential(pluginId)
      const prior = lastHost(pluginId)
      if (prior) void saveHostSurface(pluginId, { ...prior, open: false }).catch(() => {})
    } else toastBus.error(t('surface.closeFailed'))
    return closed
  }
  const standing = overlaySurface(pluginId)
  if (standing) {
    releaseSurfaceCredential(pluginId)
    const prior = lastHost(pluginId)
    const closedHost: HostSurface = prior ?? {
      slot: 'overlay',
      x: Math.round(standing.bounds.x),
      y: Math.round(standing.bounds.y),
      width: Math.round(standing.bounds.width),
      height: Math.round(standing.bounds.height),
      open: false,
      minimized: standing.minimized,
      placed: true,
    }
    useChatStore.getState().closeOverlay(standing.key)
    void saveHostSurface(pluginId, { ...closedHost, open: false }).catch(() => {})
    return overlaySurface(pluginId) === undefined
  }
  return false
}

/**
 * How often a standing surface asks to keep its credential. The server lifetime
 * is 300 s. A hidden tab may delay a timer by about a minute, and this gap still
 * lands inside that lifetime. A fetch of the document does not move the clock.
 */
export const SURFACE_RENEW_MS = 60_000

type CredentialHold = {
  nonce: string
  timer: ReturnType<typeof setInterval>
  descriptor: SurfaceDescriptor
  replacing: boolean
}

const credentialHolds = new Map<string, CredentialHold>()
let credentialWatch: (() => void) | null = null

function credentialSegment(pluginId: string, url: string): string {
  let pathname = url
  try {
    pathname = new URL(url, 'http://127.0.0.1').pathname
  } catch {
    return ''
  }
  const prefix = `/api/plugins/ui/${encodeURIComponent(pluginId)}/`
  if (!pathname.startsWith(prefix)) return ''
  const segment = pathname.slice(prefix.length).split('/')[0]
  if (!segment) return ''
  try {
    return decodeURIComponent(segment)
  } catch {
    return ''
  }
}

/** Stop asking the server to keep this plugin's mount credential. */
export function releaseSurfaceCredential(pluginId: string): void {
  const held = credentialHolds.get(pluginId)
  if (!held) return
  clearInterval(held.timer)
  credentialHolds.delete(pluginId)
}

/** Drop every standing renewal. Tests use this so a timer does not outlive a case. */
export function releaseEverySurfaceCredential(): void {
  for (const pluginId of [...credentialHolds.keys()]) releaseSurfaceCredential(pluginId)
}

function watchCredentialRenewal(): void {
  if (credentialWatch || typeof document === 'undefined') return
  const onVisibility = () => {
    if (document.visibilityState !== 'visible') return
    for (const [pluginId, held] of [...credentialHolds.entries()]) {
      void renewHeld(pluginId, held.nonce)
    }
  }
  document.addEventListener('visibilitychange', onVisibility)
  credentialWatch = () => document.removeEventListener('visibilitychange', onVisibility)
}

function holdSurfaceCredential(pluginId: string, url: string, descriptor: SurfaceDescriptor): void {
  releaseSurfaceCredential(pluginId)
  const nonce = credentialSegment(pluginId, url)
  if (!nonce) return
  watchCredentialRenewal()
  const timer = setInterval(() => {
    void renewHeld(pluginId, nonce)
  }, SURFACE_RENEW_MS)
  credentialHolds.set(pluginId, { nonce, timer, descriptor, replacing: false })
}

async function renewHeld(pluginId: string, nonce: string): Promise<void> {
  const held = credentialHolds.get(pluginId)
  if (!held || held.nonce !== nonce || held.replacing) return
  if (!isPluginSurfaceOpen(pluginId)) {
    releaseSurfaceCredential(pluginId)
    return
  }
  try {
    const next = await renewSurfaceCredential(pluginId, nonce)
    const current = credentialHolds.get(pluginId)
    if (!current || current.nonce !== nonce || current.replacing) return
    if (next !== nonce) {
      current.replacing = true
      await installStandingCredential(pluginId, next, current.descriptor)
    }
  } catch (cause) {
    if (!(cause instanceof ApiError) || cause.status !== 401) return
    const current = credentialHolds.get(pluginId)
    if (!current || current.nonce !== nonce || current.replacing) return
    if (!isPluginSurfaceOpen(pluginId)) {
      releaseSurfaceCredential(pluginId)
      return
    }
    current.replacing = true
    await remountWithFreshCredential(pluginId)
  }
}

async function remountWithFreshCredential(pluginId: string): Promise<void> {
  const held = credentialHolds.get(pluginId)
  if (!held) return
  held.replacing = true
  let nonce = ''
  try {
    nonce = await mintSurfaceCredential(pluginId)
  } catch {
    held.replacing = false
    return
  }
  await installStandingCredential(pluginId, nonce, held.descriptor)
}

async function installStandingCredential(
  pluginId: string,
  nonce: string,
  descriptor: SurfaceDescriptor,
): Promise<void> {
  const held = credentialHolds.get(pluginId)
  if (!isPluginSurfaceOpen(pluginId)) {
    releaseSurfaceCredential(pluginId)
    return
  }
  const url = surfaceMountUrl(pluginId, nonce)
  if (canOpenNativeSurface() && isNativeSurfaceOpen(pluginId)) {
    try {
      const info = await openPluginSurface(pluginId, url, descriptor)
      if (info) nativeLedger.set(info.label, info)
    } catch {
      if (held) held.replacing = false
      return
    }
  } else if (overlaySurface(pluginId)) {
    useChatStore.getState().retargetOverlay(pluginId, url)
  } else {
    releaseSurfaceCredential(pluginId)
    return
  }
  holdSurfaceCredential(pluginId, url, descriptor)
}
