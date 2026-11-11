/**
 * A restart mints a fresh mount and puts the saved box back.
 *
 * The record names the placement the shell wrote, and the two halves differ in one
 * direction only: a native record has nothing to restore in a browser tab, while an
 * overlay or canvas-overlay record restores on both. The bug this pins is the old
 * filter comparing the slot with the platform itself, which skipped every frame on
 * the desktop.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const platform = vi.hoisted(() => ({ desktop: false }))

const show = vi.fn<(req: unknown, t: unknown) => Promise<{ opened: boolean }>>(async () => ({
  opened: true,
}))
const load = vi.fn<() => Promise<Record<string, unknown>>>(async () => ({}))
const ask = vi.fn<
  (path: string, init?: unknown) => Promise<{ public: unknown[]; personal: unknown[] }>
>(async () => ({ public: [], personal: [] }))

vi.mock('@/lib/pluginDisplay', () => ({
  showPluginSurface: (req: unknown, t: unknown) => show(req, t),
}))

vi.mock('@/lib/pluginSurface', () => ({
  canOpenNativeSurface: () => platform.desktop,
}))

vi.mock('@/lib/surfaceHost', () => ({
  loadHostSurfaces: () => load(),
}))

vi.mock('@/lib/api/http', () => ({
  request: (path: string, init?: unknown) => ask(path, init),
}))

import { resetHostRestore, restoreHostSurfaces } from './restoreHostSurfaces'

const t = (key: string) => key

const record = (slot: string, over: Record<string, unknown> = {}) => ({
  slot,
  x: 40,
  y: 64,
  width: 300,
  height: 200,
  open: true,
  minimized: false,
  placed: true,
  ...over,
})

const surface = { type: 'floating-window', entry: 'index.html', title: 'Count' }

function onePlugin(id: string, over: Record<string, unknown> = {}) {
  load.mockResolvedValue({ [id]: record('overlay', over) })
  ask.mockResolvedValue({
    public: [{ name: id, surface }],
    personal: [],
  })
}

beforeEach(() => {
  platform.desktop = false
  show.mockClear()
  load.mockReset()
  ask.mockReset()
  resetHostRestore()
})

describe('restoring host surfaces', () => {
  it('opens an overlay record with its box and skips a native record in a tab', async () => {
    load.mockResolvedValue({
      countdown: record('overlay'),
      desk: record('native', { x: 1, y: 2, width: 480, height: 320 }),
    })
    ask.mockResolvedValue({
      public: [
        {
          name: 'countdown',
          surface: { type: 'floating-window', entry: 'index.html', title: 'Count' },
        },
      ],
      personal: [],
    })
    await restoreHostSurfaces(t)
    expect(show).toHaveBeenCalledTimes(1)
    expect(show).toHaveBeenCalledWith(
      expect.objectContaining({
        pluginId: 'countdown',
        host: expect.objectContaining({ x: 40, y: 64, placed: true }),
      }),
      t,
    )
    const request = show.mock.calls[0]?.[0] as { url?: string }
    expect(request.url).toBeUndefined()
  })

  /// The defect: `(slot === 'native') !== desktop` sent an overlay record back to sleep
  /// on the desktop, where the frame is exactly what the previous session had standing.
  it('restores an overlay record on the desktop', async () => {
    platform.desktop = true
    onePlugin('countdown')
    await restoreHostSurfaces(t)
    expect(show).toHaveBeenCalledTimes(1)
    expect(show).toHaveBeenCalledWith(
      expect.objectContaining({
        pluginId: 'countdown',
        host: expect.objectContaining({ slot: 'overlay' }),
      }),
      t,
    )
  })

  it('restores a canvas-overlay record on both halves', async () => {
    for (const desktop of [false, true]) {
      platform.desktop = desktop
      resetHostRestore()
      show.mockClear()
      onePlugin('canvas')
      load.mockResolvedValue({ canvas: record('canvas-overlay') })
      await restoreHostSurfaces(t)
      expect(show).toHaveBeenCalledTimes(1)
      expect(show).toHaveBeenCalledWith(expect.objectContaining({ pluginId: 'canvas' }), t)
    }
  })

  it('restores a native record in the shell', async () => {
    platform.desktop = true
    onePlugin('desk')
    load.mockResolvedValue({ desk: record('native') })
    await restoreHostSurfaces(t)
    expect(show).toHaveBeenCalledTimes(1)
    expect(show).toHaveBeenCalledWith(
      expect.objectContaining({
        pluginId: 'desk',
        host: expect.objectContaining({ slot: 'native' }),
      }),
      t,
    )
  })

  it('leaves a closed record closed on both halves', async () => {
    platform.desktop = true
    onePlugin('closed')
    load.mockResolvedValue({ closed: record('overlay', { open: false }) })
    await restoreHostSurfaces(t)
    expect(show).not.toHaveBeenCalled()
  })

  it('skips a record whose bundle no longer shows a surface', async () => {
    onePlugin('gone')
    ask.mockResolvedValue({ public: [], personal: [] })
    await restoreHostSurfaces(t)
    expect(show).not.toHaveBeenCalled()
  })
})
