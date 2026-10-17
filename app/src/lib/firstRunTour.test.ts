import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadTourMarker, shouldOpenTour, type TourMarker } from './firstRunTour'

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

  it('answers the defaults when the backend is down', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline')
      }),
    )
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
    const loaded = await loadTourMarker()
    expect(loaded.step).toBe(5)
    expect(loaded.exists).toBe(true)
  })
})
