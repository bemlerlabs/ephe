/**
 * A restart mints a fresh mount and puts the saved box back.
 * The other platform's record stays closed on this one.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  canOpenNativeSurface: () => false,
}))

vi.mock('@/lib/surfaceHost', () => ({
  loadHostSurfaces: () => load(),
}))

vi.mock('@/lib/api/http', () => ({
  request: (path: string, init?: unknown) => ask(path, init),
}))

import { resetHostRestore, restoreHostSurfaces } from './restoreHostSurfaces'

const t = (key: string) => key

beforeEach(() => {
  show.mockClear()
  load.mockReset()
  ask.mockReset()
  resetHostRestore()
})

describe('restoring host surfaces', () => {
  it('opens an overlay record with its box and skips a native record', async () => {
    load.mockResolvedValue({
      countdown: {
        slot: 'overlay',
        x: 40,
        y: 64,
        width: 300,
        height: 200,
        open: true,
        minimized: false,
        placed: true,
      },
      desk: {
        slot: 'native',
        x: 1,
        y: 2,
        width: 480,
        height: 320,
        open: true,
        minimized: false,
        placed: true,
      },
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
})
