/**
 * W1-5 — the one decision: a surface opens as a window or as a frame, and a refusal
 * reaches the user in the words of the layer that refused it.
 *
 * Both halves run for real here: `window.__TAURI__` is installed or absent, so
 * `canOpenNativeSurface()` answers the way it does in the product, and the store the dock
 * paints from is the app's own. The mock stays where a live process would sit — the shell
 * command, the HTTP mint — and every case asks the two questions the owner rule makes
 * testable: did the chosen side answer, and did the other side stay untouched?
 *
 * Out of reach in a unit run, and written where it belongs: what a shipped shell does with
 * a `plugin-window:closed` report once a browser pane holds the workbench label (#69), and
 * whether a frame paints the address it was handed (#44 pins the frame's own attributes,
 * and #50 puts a real plugin behind it).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/surfaceHost', () => ({
  saveHostSurface: vi.fn(async () => {}),
  lastHost: () => undefined,
  loadHostSurfaces: async () => ({}),
  hostRecord: (value: unknown) => value,
}))
import { useChatStore } from '@/store'
import { EMPTY_STACK, type OverlayStack } from '@/components/shell/overlayModel'
import { toastBus, type ToastItem } from '@/lib/toast'
import { saveHostSurface } from '@/lib/surfaceHost'
import {
  canOpenNativeSurface,
  nativeSurfaceLabel,
  type SurfaceDescriptor,
  type SurfaceInfo,
} from '@/lib/pluginSurface'
import {
  isNativeSurfaceOpen,
  isPluginSurfaceOpen,
  releaseEverySurfaceCredential,
  showPluginSurface,
  SURFACE_RENEW_MS,
} from '@/lib/pluginDisplay'

type Handler = (event: { payload: unknown }) => void

const invoke = vi.fn(
  async (_cmd: string, _args?: Record<string, unknown>): Promise<unknown> => undefined,
)
const listen = vi.fn(async (_name: string, _handler: Handler) => () => undefined)
const mint = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
  jsonResponse({ plugin: 'a', surface: 'n0nce' }),
)

function shell(value: unknown) {
  Object.defineProperty(window, '__TAURI__', { value, configurable: true, writable: true })
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response
}

/// The route's own shape for a refusal: a message, and no reason code the register
/// would answer from. `request()` turns exactly this envelope into an `ApiError`.
function refused(status: number, message: string): Response {
  return {
    ok: false,
    status,
    statusText: 'Refused',
    json: async () => ({ error: { message, reason_code: '' } }),
  } as unknown as Response
}

/** The copy lookup, kept as the key it was given: a test reads the key, the product reads
 *  `surface.*` in both catalogs. */
const t = (key: string): string => key

const descriptor = (over: Partial<SurfaceDescriptor> = {}): SurfaceDescriptor => ({
  type: 'floating-window',
  title: 'Countdown',
  width: 360,
  height: 240,
  transparent: true,
  always_on_top: true,
  ...over,
})

/** What `plugin_window_open` answers: the window the shell built, in the camelCase the
 *  Rust struct writes. */
const windowFor = (pluginId: string, over: Partial<SurfaceInfo> = {}): SurfaceInfo => ({
  label: nativeSurfaceLabel(pluginId),
  width: 360,
  height: 240,
  transparent: true,
  decorations: false,
  alwaysOnTop: true,
  created: true,
  note: '',
  ...over,
})

let toasts: ToastItem[] = []
let unsubscribe: () => void = () => undefined

beforeEach(() => {
  invoke.mockClear()
  // `listen` keeps its calls across cases: the shell's event channel is attached once per
  // module, the same way one `pluginDisplay` import attaches it in one running app.
  mint.mockClear()
  mint.mockImplementation(async () => jsonResponse({ plugin: 'a', surface: 'n0nce' }))
  vi.mocked(saveHostSurface).mockClear()
  useChatStore.setState({ overlay: EMPTY_STACK })
  toasts = []
  unsubscribe = toastBus.subscribe((item) => toasts.push(item))
  vi.stubGlobal('fetch', mint)
})

afterEach(() => {
  releaseEverySurfaceCredential()
  unsubscribe()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

const stack = (): OverlayStack => useChatStore.getState().overlay
const surfaceOf = (pluginId: string) => stack().surfaces.find((s) => s.pluginId === pluginId)
const errors = () => toasts.filter((item) => item.kind === 'error')
const notices = () => toasts.filter((item) => item.kind === 'info')

/** The handler the shell's event channel was given for one named event. */
function fire(eventName: string, payload: unknown) {
  const call = listen.mock.calls.find((entry) => entry[0] === eventName)
  if (!call) throw new Error(`${eventName} has no listener`)
  ;(call[1] as Handler)({ payload })
}

describe('a surface asked for in the desktop shell', () => {
  beforeEach(() => {
    shell({ core: { invoke }, event: { listen } })
  })

  it('opens the window the shell builds and leaves the overlay stack empty', async () => {
    invoke.mockResolvedValueOnce(windowFor('desk-built'))
    const outcome = await showPluginSurface({ pluginId: 'desk-built', descriptor: descriptor() }, t)
    expect(outcome).toMatchObject({
      opened: true,
      side: 'native',
      created: true,
      handle: 'ephe-plugin-desk-built',
      message: '',
    })
    expect(stack().surfaces).toEqual([])
  })

  /// The address is the one thing both halves mount, and on this side the shell checks it
  /// against the surface route before it builds anything. A window opened at an address
  /// with no credential segment loads a page the server refuses.
  it('buys the credential and hands the shell the mount address', async () => {
    invoke.mockResolvedValueOnce(windowFor('desk-url'))
    await showPluginSurface({ pluginId: 'desk-url', descriptor: descriptor() }, t)
    expect(mint).toHaveBeenCalledTimes(1)
    expect(invoke).toHaveBeenCalledWith('plugin_window_open', {
      pluginId: 'desk-url',
      url: '/api/plugins/ui/desk-url/n0nce/',
      descriptor: expect.objectContaining({ type: 'floating-window', always_on_top: true }),
    })
  })

  /// The owner rule, in the direction that has an attractive workaround: a refused window
  /// has to stay a refusal. A frame opened here would show the plugin on the wrong surface
  /// while the user kept looking for the window.
  it('carries the shell refusal to the user and opens no overlay', async () => {
    invoke.mockRejectedValueOnce('this surface type has no native window yet')
    const outcome = await showPluginSurface(
      { pluginId: 'desk-refused', descriptor: descriptor() },
      t,
    )
    expect(outcome).toMatchObject({ opened: false, side: null, message: 'surface.nativeRefused' })
    expect(errors()).toEqual([
      expect.objectContaining({
        title: 'surface.nativeRefused',
        description: 'this surface type has no native window yet',
      }),
    ])
    expect(stack().surfaces).toEqual([])
    expect(isPluginSurfaceOpen('desk-refused')).toBe(false)
  })

  /// A command that answers with nothing means the channel went away mid-call. Read as a
  /// success it hands back `undefined.label`, and the user is told nothing at all.
  it('names a command that answered nothing instead of reporting a window', async () => {
    invoke.mockResolvedValueOnce(undefined)
    const outcome = await showPluginSurface(
      { pluginId: 'desk-silent', descriptor: descriptor() },
      t,
    )
    expect(outcome.opened).toBe(false)
    expect(errors()).toEqual([
      expect.objectContaining({ title: 'surface.nativeRefused', description: undefined }),
    ])
    expect(stack().surfaces).toEqual([])
  })

  /// W1-3 measured a second open as a reveal with `created=false`. It is still the desktop
  /// answer, so the stack the dock paints from stays out of it either way.
  it('reports a reveal as the desktop half showing the surface', async () => {
    invoke.mockResolvedValueOnce(windowFor('desk-reveal', { created: false }))
    const outcome = await showPluginSurface(
      { pluginId: 'desk-reveal', descriptor: descriptor() },
      t,
    )
    expect(outcome).toMatchObject({ opened: true, side: 'native', created: false })
    expect(errors()).toEqual([])
    expect(stack().surfaces).toEqual([])
    expect(isPluginSurfaceOpen('desk-reveal')).toBe(true)
  })

  /// The ledger is what a later "is it standing?" reads, and the close belongs to the
  /// shell: the surface's own title bar ends the window and only the event says so.
  it('follows the surface down when the shell reports it closed', async () => {
    invoke.mockResolvedValueOnce(windowFor('desk-closed'))
    await showPluginSurface({ pluginId: 'desk-closed', descriptor: descriptor() }, t)
    expect(isNativeSurfaceOpen('desk-closed')).toBe(true)
    fire('plugin-window:closed', 'ephe-plugin-desk-closed')
    expect(isNativeSurfaceOpen('desk-closed')).toBe(false)
    expect(isPluginSurfaceOpen('desk-closed')).toBe(false)
  })

  /// The note is the shell's curated sentence about a window that is not the shape it was
  /// asked for; kept on the outcome and read out, so a widget that landed decorated is
  /// something the user can act on.
  it('reads out the note the shell wrote about the window it built', async () => {
    const note = 'transparency refused: this platform cannot prove a compositor'
    invoke.mockResolvedValueOnce(windowFor('desk-note', { note, transparent: false }))
    const outcome = await showPluginSurface({ pluginId: 'desk-note', descriptor: descriptor() }, t)
    expect(outcome.note).toBe(note)
    expect(notices()).toEqual([
      expect.objectContaining({ title: 'surface.landedDifferently', description: note }),
    ])
  })

  /// One mint covers both halves, so a route that refuses the surface has to stop the call
  /// before either side is asked. A window built at an address the server refuses would
  /// open a frame that shows an error page.
  it('refuses before either half when the mint has no surface to name', async () => {
    mint.mockResolvedValueOnce(refused(404, 'the manifest declares no components.ui surface'))
    const outcome = await showPluginSurface(
      { pluginId: 'desk-nomint', descriptor: descriptor() },
      t,
    )
    expect(outcome).toMatchObject({ opened: false, message: 'surface.cannotMount' })
    expect(invoke).not.toHaveBeenCalled()
    expect(stack().surfaces).toEqual([])
    expect(errors()[0]?.description).toBe('the manifest declares no components.ui surface')
  })

  it('honours always_on_top where a window server can honour it', async () => {
    invoke.mockResolvedValueOnce(windowFor('desk-ontop'))
    const outcome = await showPluginSurface({ pluginId: 'desk-ontop', descriptor: descriptor() }, t)
    expect(outcome.unmet).toEqual([])
    expect(notices()).toEqual([])
  })
})

describe('the same surface in a browser tab', () => {
  beforeEach(() => {
    shell(undefined)
  })

  /// This half is a store write the dock reads, and the geometry belongs to the viewport
  /// the caller named — the tab's own size is the fallback, decided in one place.
  it('has no native window, writes the stack, and places it in the viewport given', async () => {
    expect(canOpenNativeSurface()).toBe(false)
    const outcome = await showPluginSurface(
      {
        pluginId: 'tab-built',
        descriptor: descriptor(),
        viewport: { width: 800, height: 600 },
      },
      t,
    )
    expect(outcome).toMatchObject({
      opened: true,
      side: 'overlay',
      created: true,
      handle: 'overlay:tab-built',
    })
    expect(invoke).not.toHaveBeenCalled()
    expect(saveHostSurface).toHaveBeenCalledWith(
      'tab-built',
      expect.objectContaining({ slot: 'overlay', open: true, placed: true }),
    )
    const saved = vi.mocked(saveHostSurface).mock.calls[0]?.[1] as Record<string, unknown>
    expect(saved).not.toHaveProperty('url')
    expect(surfaceOf('tab-built')).toMatchObject({
      url: '/api/plugins/ui/tab-built/n0nce/',
      surfaceType: 'floating-window',
      title: 'Countdown',
      transparent: true,
    })
    expect(surfaceOf('tab-built')?.bounds).toEqual({ x: 220, y: 16, width: 360, height: 240 })
  })

  /// W1-3's reveal rule, carried over: a mounted document keeps the credential it was
  /// given. A second ask that re-minted and rewrote the spec would reload the plugin and
  /// drop the state on screen.
  it('reveals what already stands and mints once', async () => {
    const first = await showPluginSurface({ pluginId: 'tab-reveal', descriptor: descriptor() }, t)
    const second = await showPluginSurface(
      { pluginId: 'tab-reveal', descriptor: descriptor({ width: 900, height: 700 }) },
      t,
    )
    expect(first.created).toBe(true)
    expect(second).toMatchObject({ opened: true, side: 'overlay', created: false })
    expect(mint).toHaveBeenCalledTimes(1)
    expect(second.handle).toBe('overlay:tab-reveal')
    expect(surfaceOf('tab-reveal')?.bounds.width).toBe(360)
    expect(stack().surfaces).toHaveLength(1)
  })

  /// The same rule in the other direction: a tab that cannot mount the document says which
  /// part refused, and does not pretend a surface is on screen.
  it('says so when the tab cannot mount the document', async () => {
    mint.mockResolvedValueOnce(refused(409, 'the plugin is switched off'))
    const outcome = await showPluginSurface({ pluginId: 'tab-nomint', descriptor: descriptor() }, t)
    expect(outcome).toMatchObject({ opened: false, message: 'surface.cannotMount' })
    expect(errors()).toEqual([
      expect.objectContaining({
        title: 'surface.cannotMount',
        description: 'the plugin is switched off',
      }),
    ])
    expect(stack().surfaces).toEqual([])
  })

  /// The stack is what the dock paints from, so a write that lands nowhere is the same
  /// class of failure as a window that was never built. A no-op `openOverlay` stands in
  /// for it, because the honest outcome is a surface the user is told about.
  it('names the overlay refusal when the stack holds no surface afterwards', async () => {
    const real = useChatStore.getState().openOverlay
    useChatStore.setState({ openOverlay: () => ({ key: 'overlay:tab-hollow', created: true }) })
    try {
      const outcome = await showPluginSurface(
        { pluginId: 'tab-hollow', descriptor: descriptor() },
        t,
      )
      expect(outcome).toMatchObject({ opened: false, message: 'surface.overlayRefused' })
      expect(errors()).toEqual([expect.objectContaining({ title: 'surface.overlayRefused' })])
    } finally {
      useChatStore.setState({ openOverlay: real })
    }
  })

  /// The asymmetry the platform cannot deliver: a tab owns no screen area outside its own
  /// page. Claiming the flag would be faked parity, and silence would be the surprise.
  it('names always_on_top as a flag a tab cannot hold', async () => {
    const outcome = await showPluginSurface({ pluginId: 'tab-ontop', descriptor: descriptor() }, t)
    expect(outcome.unmet).toEqual(['always_on_top'])
    expect(notices()).toEqual([
      expect.objectContaining({
        title: 'surface.landedDifferently',
        description: 'surface.notOnTop',
      }),
    ])
  })

  it('keeps the ask quiet when the descriptor never asked to stay on top', async () => {
    const outcome = await showPluginSurface(
      { pluginId: 'tab-flat', descriptor: descriptor({ always_on_top: false }) },
      t,
    )
    expect(outcome.unmet).toEqual([])
    expect(notices()).toEqual([])
  })

  it('answers whether the surface stands, and follows the dock close', async () => {
    const opened = await showPluginSurface({ pluginId: 'tab-stand', descriptor: descriptor() }, t)
    expect(isPluginSurfaceOpen('tab-stand')).toBe(true)
    useChatStore.getState().closeOverlay(opened.handle)
    expect(isPluginSurfaceOpen('tab-stand')).toBe(false)
  })

  /// The size bound is the descriptor contract's, stated once in the validator and
  /// repeated by the shell; the browser half has to land on the same number or the two
  /// surfaces show one plugin at two sizes.
  it('carries a descriptor with no size to the contract default', async () => {
    await showPluginSurface(
      {
        pluginId: 'tab-default',
        descriptor: { type: 'floating-window', title: 'Plain' },
        viewport: { width: 1200, height: 900 },
      },
      t,
    )
    expect(surfaceOf('tab-default')?.bounds).toEqual({ x: 360, y: 16, width: 480, height: 320 })
  })
})

function showAsVisible() {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => 'visible',
  })
}

function showAsHidden() {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => 'hidden',
  })
}

describe('a standing surface keeps its credential', () => {
  beforeEach(() => {
    shell(undefined)
    showAsVisible()
  })

  it('asks the mint route again when the tab becomes visible', async () => {
    await showPluginSurface({ pluginId: 'tab-renew', descriptor: descriptor() }, t)
    expect(mint).toHaveBeenCalledTimes(1)
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(mint).toHaveBeenCalledTimes(2))
    const init = mint.mock.calls[1]?.[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ surface: 'n0nce' }))
    expect(surfaceOf('tab-renew')?.url).toBe('/api/plugins/ui/tab-renew/n0nce/')
  })

  it('leaves the clock alone while the tab is hidden', async () => {
    await showPluginSurface({ pluginId: 'tab-hidden', descriptor: descriptor() }, t)
    showAsHidden()
    document.dispatchEvent(new Event('visibilitychange'))
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(mint).toHaveBeenCalledTimes(1)
  })

  it('asks again on the renewal interval and keeps the frame URL', async () => {
    vi.useFakeTimers()
    await showPluginSurface({ pluginId: 'tab-tick', descriptor: descriptor() }, t)
    expect(mint).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(SURFACE_RENEW_MS)
    expect(mint).toHaveBeenCalledTimes(2)
    expect(surfaceOf('tab-tick')?.url).toBe('/api/plugins/ui/tab-tick/n0nce/')
  })

  it('mounts a fresh credential when the standing one is refused', async () => {
    await showPluginSurface({ pluginId: 'tab-dead', descriptor: descriptor() }, t)
    mint.mockImplementation(async (_url: string, init?: RequestInit) => {
      const raw = typeof init?.body === 'string' ? init.body : ''
      if (raw.includes('"surface"')) return refused(401, 'lost its mount credential')
      return jsonResponse({ plugin: 'a', surface: 'fresh-nonce' })
    })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() =>
      expect(surfaceOf('tab-dead')?.url).toBe('/api/plugins/ui/tab-dead/fresh-nonce/'),
    )
  })

  it('stops asking after the frame is gone', async () => {
    const opened = await showPluginSurface({ pluginId: 'tab-gone', descriptor: descriptor() }, t)
    useChatStore.getState().closeOverlay(opened.handle)
    document.dispatchEvent(new Event('visibilitychange'))
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(mint).toHaveBeenCalledTimes(1)
  })
})

describe('the desktop window keeps the same credential', () => {
  beforeEach(() => {
    shell({ core: { invoke }, event: { listen } })
    showAsVisible()
  })

  it('renews without pointing the window at a new address', async () => {
    invoke.mockImplementation(async () => windowFor('desk-keep'))
    await showPluginSurface({ pluginId: 'desk-keep', descriptor: descriptor() }, t)
    expect(invoke).toHaveBeenCalledTimes(1)
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(mint).toHaveBeenCalledTimes(2))
    expect(invoke).toHaveBeenCalledTimes(1)
  })

  it('points the window at a fresh address when the credential is refused', async () => {
    invoke.mockImplementation(async () => windowFor('desk-dead'))
    await showPluginSurface({ pluginId: 'desk-dead', descriptor: descriptor() }, t)
    mint.mockImplementation(async (_url: string, init?: RequestInit) => {
      const raw = typeof init?.body === 'string' ? init.body : ''
      if (raw.includes('"surface"')) return refused(401, 'lost its mount credential')
      return jsonResponse({ plugin: 'a', surface: 'fresh-nonce' })
    })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(invoke).toHaveBeenCalledTimes(2))
    expect(invoke).toHaveBeenLastCalledWith('plugin_window_open', {
      pluginId: 'desk-dead',
      url: '/api/plugins/ui/desk-dead/fresh-nonce/',
      descriptor: expect.objectContaining({ type: 'floating-window' }),
    })
  })
})
