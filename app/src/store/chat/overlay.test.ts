/**
 * W1-4 — the overlay stack as shell state.
 *
 * The stack lives in the app's one store, next to the other transient UI it holds,
 * so the surface that draws it and the caller that asks for it read the same object.
 * These cases pin the routing: every action hands the current stack and the caller's
 * viewport to `overlayModel` and stores the answer, and none of them touches a
 * transcript — a plugin window that moves is not a change to the session, and the
 * store's persist path must never see it.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { useChatStore } from '../chatStore'
import {
  EMPTY_STACK,
  surfaceKey,
  type SurfaceSpec,
  type Viewport,
} from '@/components/shell/overlayModel'

const VIEWPORT: Viewport = { width: 1280, height: 800 }

function spec(pluginId = 'acme-countdown'): SurfaceSpec {
  return {
    pluginId,
    title: 'Countdown',
    surfaceType: 'floating-window',
    url: 'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/',
    width: 360,
    height: 240,
    transparent: false,
  }
}

const overlay = () => useChatStore.getState().overlay
const bounds = (pluginId: string) => overlay().surfaces.find((s) => s.pluginId === pluginId)!.bounds

beforeEach(() => {
  useChatStore.setState({ overlay: EMPTY_STACK })
})

describe('the stack in the store', () => {
  it('starts with nothing open', () => {
    expect(overlay().surfaces).toEqual([])
  })

  it('opens a surface and says it was created', () => {
    expect(useChatStore.getState().openOverlay(spec(), VIEWPORT)).toEqual({
      key: surfaceKey('acme-countdown'),
      created: true,
    })
    expect(overlay().surfaces).toHaveLength(1)
    expect(bounds('acme-countdown').width).toBe(360)
  })

  it('reveals the plugin that is already standing', () => {
    const first = useChatStore.getState().openOverlay(spec(), VIEWPORT)
    const again = useChatStore.getState().openOverlay(spec(), VIEWPORT)
    expect(again.created).toBe(false)
    expect(again.key).toBe(first.key)
    expect(overlay().surfaces).toHaveLength(1)
  })

  it('keeps every surface of the stack apart', () => {
    useChatStore.getState().openOverlay(spec('acme-countdown'), VIEWPORT)
    useChatStore.getState().openOverlay(spec('acme-timer'), VIEWPORT)
    expect(overlay().surfaces.map((s) => s.pluginId)).toEqual(['acme-countdown', 'acme-timer'])
    useChatStore.getState().closeOverlay(surfaceKey('acme-countdown'))
    expect(overlay().surfaces.map((s) => s.pluginId)).toEqual(['acme-timer'])
  })

  it('moves, resizes, minimizes and restores through the model', () => {
    const key = useChatStore.getState().openOverlay(spec(), VIEWPORT).key
    useChatStore.getState().moveOverlay(key, { x: 60, y: 40 }, VIEWPORT)
    expect(bounds('acme-countdown')).toMatchObject({ x: 60, y: 40 })
    useChatStore.getState().resizeOverlay(key, { width: 420, height: 300 }, VIEWPORT)
    expect(bounds('acme-countdown')).toMatchObject({ width: 420, height: 300 })
    useChatStore.getState().minimizeOverlay(key)
    expect(overlay().surfaces[0]!.minimized).toBe(true)
    useChatStore.getState().restoreOverlay(key, VIEWPORT)
    expect(overlay().surfaces[0]!.minimized).toBe(false)
    expect(bounds('acme-countdown').y).toBe(40)
  })

  /// A phone-sized window must not leave a surface parked at desktop coordinates.
  it('clamps to the viewport the caller measured', () => {
    const key = useChatStore.getState().openOverlay(spec(), VIEWPORT).key
    useChatStore.getState().moveOverlay(key, { x: 1200, y: 700 }, VIEWPORT)
    useChatStore.getState().focusOverlay(key)
    const small: Viewport = { width: 360, height: 640 }
    useChatStore.getState().restoreOverlay(key, small)
    expect(bounds('acme-countdown').x + bounds('acme-countdown').width).toBeLessThanOrEqual(360)
  })

  it('leaves the stack untouched for a key that is not open', () => {
    useChatStore.getState().openOverlay(spec(), VIEWPORT)
    const before = overlay()
    useChatStore.getState().closeOverlay('overlay:gone')
    useChatStore.getState().focusOverlay('overlay:gone')
    useChatStore.getState().minimizeOverlay('overlay:gone')
    useChatStore.getState().moveOverlay('overlay:gone', { x: 1, y: 1 }, VIEWPORT)
    useChatStore.getState().resizeOverlay('overlay:gone', { width: 10, height: 10 }, VIEWPORT)
    useChatStore.getState().restoreOverlay('overlay:gone', VIEWPORT)
    expect(overlay()).toBe(before)
  })

  /// The reason the stack is store state and not session state: a window that
  /// moves must not make the transcript dirty, and nothing here is written down.
  it('leaves the transcript alone', () => {
    useChatStore.setState({ sessions: [], activeSessionId: null })
    useChatStore.getState().openOverlay(spec(), VIEWPORT)
    useChatStore.getState().moveOverlay(surfaceKey('acme-countdown'), { x: 10, y: 10 }, VIEWPORT)
    useChatStore.getState().closeOverlay(surfaceKey('acme-countdown'))
    expect(useChatStore.getState().sessions).toEqual([])
    expect(useChatStore.getState().activeSessionId).toBeNull()
  })
})
