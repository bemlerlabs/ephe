/**
 * W1-7 — closing a surface travels the path that mounted it.
 *
 * `hidePluginSurface` reads the same ledger `showPluginSurface` wrote: the window
 * label on the desktop, the store key in the browser. Both halves run for real
 * here, `window.__TAURI__` installed or absent, and every case asks the question
 * the owner rule makes testable — did the standing surface come down, and did the
 * answer reach the caller honestly when nothing was standing?
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/surfaceHost', () => ({
  saveHostSurface: vi.fn(async () => {}),
  lastHost: () => undefined,
  loadHostSurfaces: async () => ({}),
  hostRecord: (value: unknown) => value,
}))
import { useChatStore } from '@/store'
import { EMPTY_STACK } from '@/components/shell/overlayModel'
import { toastBus, type ToastItem } from '@/lib/toast'
import { nativeSurfaceLabel, type SurfaceDescriptor, type SurfaceInfo } from '@/lib/pluginSurface'
import {
  hidePluginSurface,
  isPluginSurfaceOpen,
  releaseEverySurfaceCredential,
  showPluginSurface,
} from '@/lib/pluginDisplay'

type Handler = (event: { payload: unknown }) => void

const invoke = vi.fn(
  async (_cmd: string, _args?: Record<string, unknown>): Promise<unknown> => undefined,
)
const listen = vi.fn(async (_name: string, _handler: Handler) => () => undefined)
const mint = vi.fn(async (): Promise<Response> => jsonResponse({ plugin: 'a', surface: 'n0nce' }))

function shell(value: unknown) {
  Object.defineProperty(window, '__TAURI__', { value, configurable: true, writable: true })
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response
}

const t = (key: string): string => key

const descriptor: SurfaceDescriptor = {
  type: 'floating-window',
  title: 'Countdown',
  width: 260,
  height: 132,
  transparent: true,
  always_on_top: true,
}

const windowFor = (pluginId: string): SurfaceInfo => ({
  label: nativeSurfaceLabel(pluginId),
  width: 260,
  height: 132,
  transparent: true,
  decorations: false,
  alwaysOnTop: true,
  created: true,
  note: '',
})

let toasts: ToastItem[] = []
let unsubscribe: () => void = () => undefined

beforeEach(() => {
  invoke.mockReset()
  invoke.mockImplementation(async () => undefined)
  mint.mockReset()
  mint.mockImplementation(async () => jsonResponse({ plugin: 'a', surface: 'n0nce' }))
  useChatStore.setState({ overlay: EMPTY_STACK })
  toasts = []
  unsubscribe = toastBus.subscribe((item) => toasts.push(item))
  vi.stubGlobal('fetch', mint)
  // Detach any window the previous case installed from the detector's view.
  shell(undefined)
})

afterEach(() => {
  releaseEverySurfaceCredential()
  unsubscribe()
  vi.unstubAllGlobals()
})

const errors = () => toasts.filter((item) => item.kind === 'error')

describe('closing a surface the desktop half mounted', () => {
  it('hands the shell the window label it opened and reports the close', async () => {
    shell({ core: { invoke }, event: { listen } })
    invoke.mockImplementation(async (cmd: string) =>
      cmd === 'plugin_window_open' ? windowFor('desk-hide') : true,
    )
    await showPluginSurface({ pluginId: 'desk-hide', descriptor }, t)
    expect(isPluginSurfaceOpen('desk-hide')).toBe(true)

    const closed = await hidePluginSurface('desk-hide', t)
    expect(closed).toBe(true)
    expect(invoke).toHaveBeenCalledWith('plugin_window_close', { handle: 'ephe-plugin-desk-hide' })
    expect(isPluginSurfaceOpen('desk-hide')).toBe(false)
    expect(errors()).toEqual([])
  })

  it('says so when the window does not confirm the close', async () => {
    shell({ core: { invoke }, event: { listen } })
    invoke.mockImplementation(async (cmd: string) =>
      cmd === 'plugin_window_open' ? windowFor('desk-stubborn') : false,
    )
    await showPluginSurface({ pluginId: 'desk-stubborn', descriptor }, t)

    const closed = await hidePluginSurface('desk-stubborn', t)
    expect(closed).toBe(false)
    expect(isPluginSurfaceOpen('desk-stubborn')).toBe(true)
    expect(errors()).toEqual([expect.objectContaining({ title: 'surface.closeFailed' })])
  })
})

describe('closing a surface the browser half mounted', () => {
  it('takes the frame down through the store the dock paints from', async () => {
    await showPluginSurface({ pluginId: 'overlay-hide', descriptor }, t)
    expect(useChatStore.getState().overlay.surfaces.map((s) => s.pluginId)).toContain(
      'overlay-hide',
    )

    const closed = await hidePluginSurface('overlay-hide', t)
    expect(closed).toBe(true)
    expect(useChatStore.getState().overlay.surfaces).toEqual([])
    expect(isPluginSurfaceOpen('overlay-hide')).toBe(false)
  })

  it('answers false when nothing was standing for this plugin', async () => {
    expect(await hidePluginSurface('never-opened', t)).toBe(false)
    expect(errors()).toEqual([])
  })
})
