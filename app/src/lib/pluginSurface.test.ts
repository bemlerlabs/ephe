/**
 * W1-3 — the bridge to a native plugin window, and the four names it speaks.
 *
 * `plugin_window_open`, `plugin_window_close` and `plugin_window_bounds` are
 * registered in `app/src-tauri/src/lib.rs` by those exact identifiers, and the
 * events the shell emits back are `plugin-window:opened` and `plugin-window:closed`.
 * A rename on either side is silent: the frontend awaits a command nobody handles
 * and the surface list never hears about a closed window. This file is the witness
 * that the two sides still say the same words, and that a browser tab without a
 * shell gets a refusal it can act on.
 *
 * What is out of reach here stays out: a unit test cannot open a webview, so the
 * window itself, its label and its capability are measured on the desktop lane.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  canOpenNativeSurface,
  closePluginSurface,
  listenNativeSurfaces,
  mintSurfaceCredential,
  renewSurfaceCredential,
  openPluginSurface,
  setPluginSurfaceBounds,
  surfaceMountUrl,
  type SurfaceEvent,
} from '@/lib/pluginSurface'

type Handler = (event: { payload: unknown }) => void

const invoke = vi.fn(
  async (_cmd: string, _args?: Record<string, unknown>): Promise<unknown> => undefined,
)
const listen = vi.fn(async (_name: string, _handler: Handler) => () => undefined)

function shell(value: unknown) {
  Object.defineProperty(window, '__TAURI__', { value, configurable: true, writable: true })
}

const descriptor = {
  type: 'floating-window',
  title: 'Countdown',
  width: 360,
  height: 240,
  transparent: true,
  always_on_top: true,
}

const SURFACE_URL = 'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/'

describe('a surface asked for in the desktop shell', () => {
  beforeEach(() => {
    invoke.mockClear()
    listen.mockClear()
    shell({ core: { invoke }, event: { listen } })
  })

  it('opens through the command the shell registered', async () => {
    await openPluginSurface('acme-countdown', SURFACE_URL, descriptor)
    expect(invoke).toHaveBeenCalledWith('plugin_window_open', {
      pluginId: 'acme-countdown',
      url: SURFACE_URL,
      descriptor,
    })
  })

  it('keeps the descriptor keys the API hands over', async () => {
    await openPluginSurface('acme-countdown', SURFACE_URL, descriptor)
    const sent = invoke.mock.calls[0]?.[1] as { descriptor: Record<string, unknown> } | undefined
    expect(sent?.descriptor.always_on_top).toBe(true)
    expect(sent?.descriptor.transparent).toBe(true)
    expect(sent?.descriptor.type).toBe('floating-window')
  })

  it('closes by handle', async () => {
    await closePluginSurface('ephe-plugin-acme-countdown')
    expect(invoke).toHaveBeenCalledWith('plugin_window_close', {
      handle: 'ephe-plugin-acme-countdown',
    })
  })

  it('moves by handle', async () => {
    await setPluginSurfaceBounds('ephe-plugin-acme-countdown', {
      x: 40,
      y: 60,
      width: 300,
      height: 200,
    })
    expect(invoke).toHaveBeenCalledWith('plugin_window_bounds', {
      handle: 'ephe-plugin-acme-countdown',
      bounds: { x: 40, y: 60, width: 300, height: 200 },
    })
  })

  /// A Rust refusal reaches the caller as a rejection, not as a swallowed `null`.
  /// `plugin_window.rs::guard_before_dispatch` answers the invoke with the curated
  /// sentence; nothing on this side catches it, so the caller hears the rule. Without
  /// this case the whole journey of a refused invoke is unpinned — the mock used never
  /// to throw.
  it('carries the shell refusal to the caller', async () => {
    invoke.mockRejectedValueOnce('plugin windows open from the Ephe window only')
    await expect(openPluginSurface('acme-countdown', SURFACE_URL, descriptor)).rejects.toBe(
      'plugin windows open from the Ephe window only',
    )
  })

  it('carries a refused move to the caller as well', async () => {
    invoke.mockRejectedValueOnce('no plugin window carries that handle')
    await expect(
      setPluginSurfaceBounds('ephe-plugin-acme-countdown', { x: 1, y: 2, width: 3, height: 4 }),
    ).rejects.toBe('no plugin window carries that handle')
  })

  /// `SurfaceInfo` is `#[serde(rename_all = "camelCase")]` in Rust, so the window
  /// flags arrive already renamed. A surface that read `always_on_top` here would get
  /// `undefined` and believe the descriptor was ignored.
  it('reads the window back with the camelCase keys Rust writes', async () => {
    const built = {
      label: 'ephe-plugin-acme-countdown',
      width: 360,
      height: 240,
      transparent: true,
      decorations: false,
      alwaysOnTop: true,
      created: true,
      note: '',
    }
    invoke.mockResolvedValueOnce(built)
    const info = await openPluginSurface('acme-countdown', SURFACE_URL, descriptor)
    expect(info).toEqual(built)
    expect(info?.decorations).toBe(false)
    expect(info?.alwaysOnTop).toBe(true)

    const seen: SurfaceEvent[] = []
    const stop = listenNativeSurfaces((event) => seen.push(event))
    const opened = listen.mock.calls.find((call) => call[0] === 'plugin-window:opened')
    ;(opened?.[1] as (e: { payload: unknown }) => void)({ payload: built })
    const first = seen[0]
    expect(first?.kind).toBe('opened')
    if (first?.kind === 'opened') {
      expect(first.info.decorations).toBe(false)
      expect(first.info.alwaysOnTop).toBe(true)
    }
    stop()
  })

  it('hears both names the shell emits', () => {
    const seen: SurfaceEvent[] = []
    const stop = listenNativeSurfaces((event) => seen.push(event))
    const opened = listen.mock.calls.find((call) => call[0] === 'plugin-window:opened')
    const closed = listen.mock.calls.find((call) => call[0] === 'plugin-window:closed')
    expect(opened).toBeDefined()
    expect(closed).toBeDefined()
    ;(opened?.[1] as (e: { payload: unknown }) => void)({
      payload: { label: 'ephe-plugin-acme-countdown', created: true },
    })
    ;(closed?.[1] as (e: { payload: unknown }) => void)({ payload: 'ephe-plugin-acme-countdown' })
    expect(seen.map((event) => event.kind)).toEqual(['opened', 'closed'])
    stop()
  })
})

describe('the same surface in a browser tab', () => {
  beforeEach(() => {
    shell(undefined)
  })

  it('says there is no native window to ask', () => {
    expect(canOpenNativeSurface()).toBe(false)
  })

  it('returns nothing rather than throwing at the caller', async () => {
    await expect(openPluginSurface('acme-countdown', SURFACE_URL, descriptor)).resolves.toBeNull()
    await expect(closePluginSurface('ephe-plugin-acme-countdown')).resolves.toBe(false)
    expect(listenNativeSurfaces(() => undefined)).toBeTypeOf('function')
  })
})

/**
 * W1-4 — the half both surfaces share. The overlay dock is a `<frame>` with no way
 * to add a header to the document it loads or to the files that document derives,
 * so the credential is a path segment (#42, RW2) and the URL is directory-shaped
 * because that slash is where relative resolution starts.
 */
describe('the mount URL and the credential it carries', () => {
  it('is the directory shape with the nonce as one of its segments', () => {
    expect(surfaceMountUrl('acme-countdown', 'n0nce', '')).toBe(
      '/api/plugins/ui/acme-countdown/n0nce/',
    )
  })

  it('keeps the base the caller resolves, so one URL serves loopback and LAN', () => {
    expect(surfaceMountUrl('acme-countdown', 'n0nce', 'http://127.0.0.1:8765')).toBe(
      'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/',
    )
  })

  /// The long-lived LAN token never belongs in a URL (#42 R21: logs, history and
  /// screenshots all keep a query). A frame can only carry what the path holds.
  it('puts no token in a query on any path', () => {
    for (const url of [
      surfaceMountUrl('acme-countdown', 'n0nce', ''),
      surfaceMountUrl('acme-countdown', 'n0nce', 'http://127.0.0.1:8765'),
    ]) {
      expect(url).not.toContain('?')
      expect(url.toLowerCase()).not.toContain('token')
    }
  })

  it('encodes an id the filesystem allows and a path segment does not', () => {
    expect(surfaceMountUrl('ä日😀', 'n0nce', '')).toBe(
      '/api/plugins/ui/%C3%A4%E6%97%A5%F0%9F%98%80/n0nce/',
    )
  })

  it('mints through the authenticated POST the route is guarded by', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ plugin: 'a', surface: 'n0nce', expires_in: 300 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    try {
      expect(await mintSurfaceCredential('acme-countdown')).toBe('n0nce')
      const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
      expect(url).toContain('/api/plugins/acme-countdown/surface-token')
      expect(init.method).toBe('POST')
      expect(new Headers(init.headers).get('X-Requested-With')).toBe('XMLHttpRequest')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  /// A surface that cannot be mounted is refused by the mint (`_declared_surface`),
  /// and a mint that swallowed that would leave the dock holding an empty frame.
  it('lets a refusal reach the caller with its status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ error: { message: 'no surface declared', reason_code: '' } }),
      })),
    )
    try {
      await expect(mintSurfaceCredential('acme-countdown')).rejects.toMatchObject({ status: 404 })
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('renews by posting the standing credential to the same route', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ plugin: 'a', surface: 'n0nce', expires_in: 300 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    try {
      expect(await renewSurfaceCredential('acme-countdown', 'n0nce')).toBe('n0nce')
      const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
      expect(url).toContain('/api/plugins/acme-countdown/surface-token')
      expect(init.method).toBe('POST')
      expect(init.body).toBe(JSON.stringify({ surface: 'n0nce' }))
      expect(new Headers(init.headers).get('X-Requested-With')).toBe('XMLHttpRequest')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response
}
