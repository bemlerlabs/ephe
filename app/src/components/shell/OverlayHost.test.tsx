/**
 * W1-4 — the overlay host: what a plugin surface looks like in a browser tab.
 *
 * The frame is the boundary #42 paid for, so the attribute set comes first:
 * `sandbox` with the same effect as the document's own CSP (`allow-scripts
 * allow-popups`, with `allow-same-origin` left out), measured in a real engine by
 * `w1-4-report.md` for what it does and does not take away. The rest is the
 * keyboard contract: a surface that floats over the workbench must not take the
 * composer with it, must answer Escape, and must leave every control reachable by
 * name and by Tab.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import '@/i18n'
import { readFileSync } from 'node:fs'
import OverlayHost from './OverlayHost'
import { useChatStore } from '@/store'
import { EMPTY_STACK, surfaceKey, type SurfaceSpec, type Viewport } from './overlayModel'
import { tabStops } from '@/hooks/useFocusReturn'

const VIEWPORT: Viewport = { width: 1280, height: 800 }

function spec(pluginId = 'acme-countdown', over: Partial<SurfaceSpec> = {}): SurfaceSpec {
  return {
    pluginId,
    title: 'Countdown',
    surfaceType: 'floating-window',
    url: `http://127.0.0.1:8765/api/plugins/ui/${pluginId}/n0nce/`,
    width: 360,
    height: 240,
    transparent: false,
    ...over,
  }
}

/** Opens through the store, the way the shell's own caller does. A write from
 * outside the component needs `act`: the host subscribes, and React only flushes
 * the re-render at the end of the task. */
function open(pluginId = 'acme-countdown', over: Partial<SurfaceSpec> = {}) {
  act(() => useChatStore.getState().openOverlay(spec(pluginId, over), VIEWPORT))
}

const frame = () => document.querySelector('iframe')
const window_ = () => document.querySelector('[data-overlay-window]')
const css = readFileSync('src/components/shell/OverlayHost.css', 'utf8')

/** The host reads the viewport live; jsdom's own is 1024x768. */
function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width })
  Object.defineProperty(window, 'innerHeight', {
    configurable: true,
    writable: true,
    value: height,
  })
}

beforeEach(() => {
  setViewport(VIEWPORT.width, VIEWPORT.height)
  act(() => useChatStore.setState({ overlay: EMPTY_STACK }))
})

describe('the frame a plugin document arrives in', () => {
  it('paints nothing while the stack is empty', () => {
    const { container } = render(<OverlayHost />)
    expect(container.innerHTML).toBe('')
  })

  it('mounts the URL #42 serves, credential in the path', () => {
    render(<OverlayHost />)
    open()
    expect(frame()?.getAttribute('src')).toBe(
      'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/',
    )
  })

  /// The isolation contract, in one attribute: scripts and popups, no same-origin.
  /// `allow-same-origin` would hand an attacker-authored page the app's own origin.
  it('sandboxed with the same effect as the document policy, and no looser', () => {
    render(<OverlayHost />)
    open()
    const sandbox = frame()?.getAttribute('sandbox') ?? ''
    expect(sandbox.split(/\s+/).sort()).toEqual(['allow-popups', 'allow-scripts'])
    expect(sandbox).not.toContain('allow-same-origin')
    expect(sandbox).not.toContain('allow-top-navigation')
    expect(sandbox).not.toContain('allow-forms')
  })

  it('names the frame, denies every permissions-policy feature and leaks no referrer', () => {
    render(<OverlayHost />)
    open('acme-countdown', { title: 'Release countdown' })
    expect(frame()?.getAttribute('title')).toBe('Release countdown')
    expect(frame()?.getAttribute('allow')).toBe('')
    expect(frame()?.getAttribute('referrerpolicy')).toBe('no-referrer')
  })

  it('keeps one surface per plugin, as the desktop label does', () => {
    render(<OverlayHost />)
    open()
    open()
    expect(document.querySelectorAll('iframe')).toHaveLength(1)
  })

  it('carries the descriptor that drives the window', () => {
    render(<OverlayHost />)
    open('acme-countdown', { transparent: true, width: 300, height: 200 })
    expect(window_()?.getAttribute('data-transparent')).toBe('true')
    expect(window_()?.getAttribute('data-surface-type')).toBe('floating-window')
    expect(window_()?.getAttribute('style')).toContain('width: 300px')
  })

  /// `always_on_top` has no browser equivalent, so the field never reaches this
  /// half: the model has no place for it and the DOM claims nothing. A fake
  /// "always on top" affordance would read as support the browser cannot give.
  it('claims no always-on-top of its own', () => {
    render(<OverlayHost />)
    open()
    expect(window_()?.hasAttribute('data-always-on-top')).toBe(false)
    expect(Object.keys(useChatStore.getState().overlay.surfaces[0] ?? {})).not.toContain(
      'always_on_top',
    )
  })

  it('tears the frame down on unmount, and revokes nothing it never created', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    const { unmount } = render(<OverlayHost />)
    open()
    expect(frame()).toBeTruthy()
    unmount()
    expect(frame()).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})

describe('the stack order', () => {
  it('puts the focused surface above the others', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    const rank = (pluginId: string) =>
      document
        .querySelector(`[data-overlay-window][data-plugin="${pluginId}"]`)
        ?.getAttribute('style')
        ?.match(/--stack-rank: (\d+)/)?.[1]
    expect(rank('a')).toBe('0')
    expect(rank('b')).toBe('1')
    act(() => useChatStore.getState().focusOverlay(surfaceKey('a')))
    expect(rank('a')).toBe('1')
    expect(rank('b')).toBe('0')
  })
})

describe('the keyboard contract', () => {
  it('gives each window control an accessible name', () => {
    render(
      <>
        <input id="ephe-chat-input" aria-label="composer" />
        <OverlayHost />
      </>,
    )
    open()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Minimize' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Close' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Resize surface' })).toBeTruthy()
  })

  it('puts the rail controls ahead of the resize grip in tab order', () => {
    render(<OverlayHost />)
    open()
    const stops = tabStops(document.querySelector('[data-overlay-window]') as HTMLElement).map(
      (el) => el.getAttribute('aria-label'),
    )
    expect(stops).toEqual(['Reload', 'Minimize', 'Close', 'Resize surface'])
  })

  /// Not a modal: the page behind stays reachable, so the composer never goes inert
  /// and Tab leaves the surface the way it entered.
  it('leaves the rest of the app reachable', () => {
    render(
      <>
        <input id="ephe-chat-input" aria-label="composer" />
        <OverlayHost />
      </>,
    )
    open()
    expect(document.querySelector('[inert]')).toBeNull()
    const input = document.getElementById('ephe-chat-input') as HTMLElement
    input.focus()
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(useChatStore.getState().overlay.surfaces[0]?.minimized).toBe(false)
  })

  it('minimizes on Escape from the surface and moves focus to the restore control', () => {
    render(<OverlayHost />)
    open()
    const grip = screen.getByRole('button', { name: 'Resize surface' })
    grip.focus()
    fireEvent.keyDown(grip, { key: 'Escape' })
    expect(useChatStore.getState().overlay.surfaces[0]?.minimized).toBe(true)
    expect(document.activeElement?.getAttribute('aria-label')).toBe('Maximize')
    expect(document.activeElement?.tagName).toBe('BUTTON')
  })

  it('restores from the rail and keeps the frame mounted', () => {
    render(<OverlayHost />)
    open()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Minimize' }), { key: 'Escape' })
    expect(frame()?.hasAttribute('hidden')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Maximize' }))
    expect(useChatStore.getState().overlay.surfaces[0]?.minimized).toBe(false)
    expect(frame()?.hasAttribute('hidden')).toBe(false)
  })

  it('resizes by keyboard, inside the floor the controls need', () => {
    render(<OverlayHost />)
    open()
    const grip = screen.getByRole('button', { name: 'Resize surface' })
    fireEvent.keyDown(grip, { key: 'ArrowRight' })
    expect(useChatStore.getState().overlay.surfaces[0]?.bounds.width).toBe(376)
    for (let i = 0; i < 40; i++) fireEvent.keyDown(grip, { key: 'ArrowLeft' })
    const width = useChatStore.getState().overlay.surfaces[0]?.bounds.width
    expect(width).toBeGreaterThanOrEqual(220)
  })
})

describe('pointer work on the geometry', () => {
  it('drags by the rail and releases the pointer', () => {
    render(<OverlayHost />)
    open()
    const rail = screen.getByTestId('overlay-rail')
    const move = useChatStore.getState().moveOverlay
    const spy = vi.spyOn(useChatStore.getState(), 'moveOverlay')
    fireEvent.pointerDown(rail, { pointerId: 1, clientX: 100, clientY: 100, button: 0 })
    fireEvent.pointerMove(rail, { pointerId: 1, clientX: 140, clientY: 130 })
    fireEvent.pointerUp(rail, { pointerId: 1 })
    expect(spy).toHaveBeenCalledWith(surfaceKey('acme-countdown'), { x: 500, y: 46 }, VIEWPORT)
    expect(move).toBeDefined()
  })

  it('raises the surface the pointer lands on', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    const zOf = (pluginId: string) =>
      useChatStore.getState().overlay.surfaces.find((s) => s.pluginId === pluginId)!.z
    fireEvent.pointerDown(screen.getAllByTestId('overlay-rail')[0]!, {
      pointerId: 2,
      clientX: 0,
      clientY: 0,
      button: 0,
    })
    expect(zOf('a')).toBeGreaterThan(zOf('b'))
  })

  it('resizes by the grip and keeps the box inside the viewport', () => {
    render(<OverlayHost />)
    open()
    const grip = screen.getByRole('button', { name: 'Resize surface' })
    fireEvent.pointerDown(grip, { pointerId: 3, clientX: 200, clientY: 200, button: 0 })
    fireEvent.pointerMove(grip, { pointerId: 3, clientX: 4000, clientY: 4000 })
    const bounds = useChatStore.getState().overlay.surfaces[0]?.bounds
    expect(bounds?.width).toBe(VIEWPORT.width)
    expect(bounds?.height).toBe(VIEWPORT.height)
    fireEvent.pointerUp(grip, { pointerId: 3 })
  })

  it('keeps a drag of one surface from moving another', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    const rails = screen.getAllByTestId('overlay-rail')
    fireEvent.pointerDown(rails[0]!, { pointerId: 4, clientX: 10, clientY: 10, button: 0 })
    fireEvent.pointerMove(rails[1]!, { pointerId: 5, clientX: 900, clientY: 900 })
    fireEvent.pointerMove(rails[0]!, { pointerId: 4, clientX: 60, clientY: 60 })
    const [first, second] = useChatStore.getState().overlay.surfaces
    expect(first?.bounds.x).toBe(510)
    expect(second?.bounds.x).toBe(488)
  })
})

describe('listeners that must not outlive the host', () => {
  it('re-clamps the stack when the viewport shrinks, and stops when unmounted', () => {
    const add = vi.spyOn(window, 'addEventListener')
    const remove = vi.spyOn(window, 'removeEventListener')
    useChatStore.setState({ overlay: EMPTY_STACK })
    const { unmount } = render(<OverlayHost />)
    open('a', { width: 600, height: 400 })
    const registered = add.mock.calls.find(([type]) => type === 'resize')
    expect(registered).toBeDefined()

    // The parked surface is now wider than the window it is in.
    act(() =>
      useChatStore.setState((s) => ({
        overlay: {
          ...s.overlay,
          surfaces: s.overlay.surfaces.map((surface) => ({
            ...surface,
            bounds: { x: 1200, y: 500, width: 600, height: 400 },
          })),
        },
      })),
    )
    setViewport(700, 500)
    fireEvent(window, new Event('resize'))
    const bounds = useChatStore.getState().overlay.surfaces[0]?.bounds
    expect(bounds?.x).toBe(100)
    expect(bounds?.y).toBe(100)

    unmount()
    expect(remove.mock.calls.some(([type]) => type === 'resize')).toBe(true)
    fireEvent(window, new Event('resize'))
    expect(useChatStore.getState().overlay.surfaces[0]?.bounds).toBe(bounds)
    add.mockRestore()
    remove.mockRestore()
  })
})

describe('the chrome budget', () => {
  it('holds the 44 px touch floor in the sheet that sizes the controls', () => {
    expect(css).toMatch(/\.overlay-control\s*\{[^}]*width:\s*44px/)
    expect(css).toMatch(/\.overlay-control\s*\{[^}]*height:\s*44px/)
    expect(css).toMatch(/\.overlay-rail\s*\{[^}]*height:\s*44px/)
  })

  it('reveals the controls on hover and on focus, and stays quiet otherwise', () => {
    expect(css).toMatch(/\.overlay-window:hover[\s\S]{0,120}\.overlay-control \{/)
    expect(css).toMatch(/:focus-within[\s\S]{0,120}\.overlay-control \{/)
    expect(css).toContain('@media (pointer: coarse)')
  })

  it('takes its material from the one floating primitive', () => {
    render(<OverlayHost />)
    open()
    const classes = window_()?.getAttribute('class') ?? ''
    expect(classes).toContain('float-surface')
    expect(css).not.toMatch(/border-radius|box-shadow|backdrop-filter/)
  })

  it('keeps a surface readable at 360x240 and at its descriptor size', () => {
    render(<OverlayHost />)
    open('acme-countdown', { width: 360, height: 240 })
    const style = window_()?.getAttribute('style') ?? ''
    expect(style).toContain('width: 360px')
    expect(style).toContain('height: 240px')
    expect(css).toMatch(/\.overlay-frame\s*\{[^}]*height:\s*calc\(100%\s*-\s*44px\)/)
  })
})

describe('closing', () => {
  it('removes the surface the button belongs to', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0]!)
    expect(useChatStore.getState().overlay.surfaces.map((s) => s.pluginId)).toEqual(['b'])
  })

  /// The handback only happens when the surface held the focus. A close from
  /// elsewhere must not pull the caret out of a composer that is mid-sentence.
  it('hands focus to a stable target when the surface had it', () => {
    render(
      <>
        <input id="ephe-chat-input" aria-label="composer" />
        <OverlayHost />
      </>,
    )
    open()
    const close = screen.getByRole('button', { name: 'Close' })
    close.focus()
    fireEvent.click(close)
    expect(document.activeElement?.id).toBe('ephe-chat-input')
  })

  it('leaves focus where it is when the surface never had it', () => {
    render(
      <>
        <input id="ephe-chat-input" aria-label="composer" />
        <OverlayHost />
      </>,
    )
    open()
    const input = document.getElementById('ephe-chat-input') as HTMLElement
    input.focus()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(document.activeElement?.id).toBe('ephe-chat-input')
  })
})
