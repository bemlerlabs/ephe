import { afterEach, describe, expect, it, vi } from 'vitest'
import { shouldOpenTour, type TourMarker } from './firstRunTour'

const marker = (overrides: Partial<TourMarker> = {}): TourMarker => ({
  version: 1,
  step: 0,
  walked: false,
  skipped: false,
  answers: {},
  exists: false,
  ...overrides,
})

const gate = (
  overrides: Partial<{ ready: boolean; configured: boolean; skipped: boolean }> = {},
) => ({
  ready: true,
  configured: false,
  skipped: false,
  ...overrides,
})

describe('shouldOpenTour', () => {
  it('opens a fresh install once the gate answered', () => {
    expect(shouldOpenTour(marker(), gate(), false)).toBe(true)
  })

  it('waits for the gate instead of deciding early', () => {
    expect(shouldOpenTour(marker(), gate({ ready: false }), false)).toBe(false)
  })

  it('resumes an interrupted marker', () => {
    expect(
      shouldOpenTour(marker({ exists: true, step: 3 }), gate({ configured: true }), false),
    ).toBe(true)
  })

  it('does not open for a configured returning install', () => {
    expect(shouldOpenTour(marker(), gate({ configured: true }), false)).toBe(false)
  })

  it('respects walked and skipped', () => {
    expect(shouldOpenTour(marker({ exists: true, walked: true }), gate(), false)).toBe(false)
    expect(shouldOpenTour(marker({ exists: true, skipped: true }), gate(), false)).toBe(false)
  })

  it('opens on the replay trigger even after a walk', () => {
    expect(
      shouldOpenTour(marker({ exists: true, walked: true }), gate({ configured: true }), true),
    ).toBe(true)
  })

  it('opens for a user who skipped the engine setup', () => {
    expect(shouldOpenTour(marker(), gate({ configured: false, skipped: true }), false)).toBe(true)
  })
})

describe('loadTourMarker', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  async function freshModule() {
    vi.resetModules()
    return import('./firstRunTour')
  }

  it('answers the defaults when the backend is down', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline')
      }),
    )
    const { loadTourMarker } = await freshModule()
    await expect(loadTourMarker()).resolves.toEqual(marker())
  })

  it('clamps a step outside the tour into the marker', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ step: 99, walked: false, exists: true, answers: {} }),
      })),
    )
    const { loadTourMarker } = await freshModule()
    const loaded = await loadTourMarker()
    expect(loaded.step).toBe(5)
    expect(loaded.exists).toBe(true)
  })

  it('coalesces two concurrent callers into one request', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ step: 1, walked: false, exists: true, answers: {} }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { loadTourMarker } = await freshModule()
    const [first, second] = await Promise.all([loadTourMarker(), loadTourMarker()])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(second).toEqual(first)
  })

  it('serves the marker a write returned without another GET', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => ({
      ok: true,
      json: async () =>
        init?.method === 'POST'
          ? { version: 1, step: 5, walked: true, skipped: false, answers: {}, exists: true }
          : { version: 1, step: 0, walked: false, skipped: false, answers: {}, exists: true },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { loadTourMarker, writeTourMarker } = await freshModule()
    const loaded = await loadTourMarker()
    const written = await writeTourMarker({ ...loaded, walked: true, step: 5 })
    const again = await loadTourMarker()
    expect(again.walked).toBe(true)
    expect(again).toEqual(written)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('retries after an offline read instead of caching the empty marker', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ step: 2, walked: false, exists: true, answers: {} }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const { loadTourMarker } = await freshModule()
    const offline = await loadTourMarker()
    expect(offline.exists).toBe(false)
    const recovered = await loadTourMarker()
    expect(recovered.exists).toBe(true)
    expect(recovered.step).toBe(2)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('retries after a non-OK read instead of caching the empty marker', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ step: 3, walked: false, exists: true, answers: {} }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const { loadTourMarker } = await freshModule()
    expect((await loadTourMarker()).exists).toBe(false)
    const recovered = await loadTourMarker()
    expect(recovered.exists).toBe(true)
    expect(recovered.step).toBe(3)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('publishes a successful marker and leaves a failed read unpublished', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ step: 2, walked: false, exists: true, answers: {} }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const { loadTourMarker, subscribeTourMarker, tourMarkerSnapshot } = await freshModule()
    const seen: boolean[] = []
    const off = subscribeTourMarker(() => seen.push(Boolean(tourMarkerSnapshot()?.exists)))
    expect(tourMarkerSnapshot()).toBeNull()
    await loadTourMarker()
    expect(tourMarkerSnapshot()).toBeNull()
    expect(seen).toEqual([])
    await loadTourMarker()
    expect(tourMarkerSnapshot()?.exists).toBe(true)
    expect(seen).toEqual([true])
    off()
  })
})
