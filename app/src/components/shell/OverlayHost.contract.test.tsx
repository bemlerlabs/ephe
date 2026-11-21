/**
 * W1-4 — what the embedder promises a plugin surface, past the rendering.
 *
 * `OverlayHost.test.tsx` covers the frame appearing and the keyboard contract. This
 * file holds the three claims a reviewer cannot take on faith, each pinned at the
 * edge the component controls:
 *
 *   - the isolation attribute, in both directions — what it refuses (same-origin,
 *     top navigation, forms, modals, downloads, escape-sandbox popups, storage
 *     access) and the fact that no descriptor field, plugin or otherwise, reaches it;
 *   - the URL shape #42 serves and the frame inherits untouched, because the trailing
 *     slash on the credential segment is what lets the document's own relative assets
 *     still resolve, and the host must add nothing of its own to the page's requests;
 *   - the numbers the shell sets for itself: the painted box order comes from the
 *     model's z, and the one height this component writes inline is the 44 px rail.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import '@/i18n'
import { readFileSync } from 'node:fs'
import OverlayHost from './OverlayHost'
import { useChatStore } from '@/store'
import {
  EMPTY_STACK,
  OVERLAY_RAIL_HEIGHT,
  surfaceKey,
  type SurfaceSpec,
  type Viewport,
} from './overlayModel'

const VIEWPORT: Viewport = { width: 1280, height: 800 }
const css = readFileSync('src/components/shell/OverlayHost.css', 'utf8')

/// Everything the presence of `allow-scripts` and `allow-popups` does not grant. A
/// frame that lost any one of these to a well-meant fix stops being the boundary
/// #42 paid for: `allow-same-origin` returns the app's own origin, the navigation
/// flags let the mount move or replace the document holding the workbench, and
/// `allow-popups-to-escape-sandbox` hands a window the mount opened back its origin.
const REFUSED = [
  'allow-same-origin',
  'allow-top-navigation',
  'allow-top-navigation-by-user-activation',
  'allow-top-navigation-to-custom-protocols',
  'allow-forms',
  'allow-modals',
  'allow-downloads',
  'allow-popups-to-escape-sandbox',
  'allow-storage-access-by-user-activation',
  'allow-pointer-lock',
  'allow-presentation',
  'allow-orientation-lock',
  'allow-encrypted-media',
]

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

function open(pluginId = 'acme-countdown', over: Partial<SurfaceSpec> = {}) {
  act(() => useChatStore.getState().openOverlay(spec(pluginId, over), VIEWPORT))
}

const frames = () => Array.from(document.querySelectorAll('iframe'))
const boxes = () => Array.from(document.querySelectorAll('[data-overlay-window]'))
const rankOf = (el: Element | null | undefined) =>
  el?.getAttribute('style')?.match(/--stack-rank: (\d+)/)?.[1] ?? null
const zOf = (pluginId: string) =>
  useChatStore.getState().overlay.surfaces.find((s) => s.pluginId === pluginId)!.z

beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1280 })
  Object.defineProperty(window, 'innerHeight', { configurable: true, writable: true, value: 800 })
  act(() => useChatStore.setState({ overlay: EMPTY_STACK }))
})

describe('the isolation attribute, in both directions', () => {
  it('grants scripts and popups and nothing else', () => {
    render(<OverlayHost />)
    open()
    const granted = frames()[0]!.getAttribute('sandbox')!.split(/\s+/).sort()
    expect(granted).toEqual(['allow-popups', 'allow-scripts'])
  })

  it('refuses every flag that would return authority to the mount', () => {
    render(<OverlayHost />)
    open()
    const sandbox = frames()[0]!.getAttribute('sandbox')!
    for (const refused of REFUSED) expect(sandbox).not.toContain(refused)
    expect(sandbox).not.toBe('')
  })

  it('carries exactly the attributes the host decided on, and no looser ones', () => {
    render(<OverlayHost />)
    open()
    const frame = frames()[0]!
    const attrs = Object.fromEntries(Array.from(frame.attributes).map((a) => [a.name, a.value]))
    expect(attrs).toEqual({
      'data-testid': 'overlay-frame-acme-countdown',
      class: 'overlay-frame',
      title: 'Countdown',
      src: 'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/',
      sandbox: 'allow-scripts allow-popups',
      allow: '',
      referrerpolicy: 'no-referrer',
    } satisfies Record<string, string>)
    expect(frame.hasAttribute('hidden')).toBe(false)
    expect(frame.hasAttribute('allowfullscreen')).toBe(false)
    expect(frame.hasAttribute('credentialless')).toBe(false)
  })

  /// A plugin ships its own `ui` descriptor, so nothing about the frame may be
  /// derived from it: the descriptor asks for size, title and transparency here,
  /// and the isolation stays the host's.
  it('never lets a descriptor loosen the frame', () => {
    render(<OverlayHost />)
    open('acme-asks-nicely', {
      surfaceType: 'dock',
      transparent: true,
      sandbox: 'allow-same-origin allow-scripts allow-forms',
      allow: 'camera;microphone;geolocation',
      referrerPolicy: 'unsafe-url',
    } as Partial<SurfaceSpec>)
    const frame = frames()[0]!
    expect(frame.getAttribute('sandbox')).toBe('allow-scripts allow-popups')
    expect(frame.getAttribute('allow')).toBe('')
    expect(frame.getAttribute('referrerpolicy')).toBe('no-referrer')
  })

  /// Seam C's first cut: a `canvas-overlay` is carried by this stack on both halves,
  /// and it is the same boundary as any other frame — the type changes placement, not
  /// isolation.
  it('paints a canvas-overlay as the same framed surface', () => {
    render(<OverlayHost />)
    open('acme-canvas', { surfaceType: 'canvas-overlay' })
    expect(boxes()).toHaveLength(1)
    expect(boxes()[0]?.getAttribute('data-surface-type')).toBe('canvas-overlay')
    expect(frames()[0]?.getAttribute('sandbox')).toBe('allow-scripts allow-popups')
    expect(frames()[0]?.getAttribute('title')).toBe('Countdown')
    expect(frames()[0]?.getAttribute('src')).toBe(
      'http://127.0.0.1:8765/api/plugins/ui/acme-canvas/n0nce/',
    )
  })

  it('puts the same directive on every surface in the stack', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    expect(frames()).toHaveLength(2)
    for (const frame of frames())
      expect(frame.getAttribute('sandbox')).toBe('allow-scripts allow-popups')
  })
})

describe('the URL the frame is pointed at', () => {
  /// The credential segment closes with a slash because that is where the browser
  /// starts resolving relative references; drop it and `<script src="app.js">` in
  /// the plugin document asks for a path with no credential, which #42 refuses.
  it('keeps the mount URL whole, slash and all, so the document loads its own assets', () => {
    render(<OverlayHost />)
    open()
    const url = useChatStore.getState().overlay.surfaces[0]!.url
    const src = frames()[0]!.getAttribute('src')!
    expect(src).toBe(url)
    expect(src).toMatch(/\/api\/plugins\/ui\/[^/]+\/[^/]+\/$/)
    expect(url.split('/').at(-2)).toBe('n0nce')
  })

  it('leaves the credential out of the query, where a proxy log would keep it', () => {
    render(<OverlayHost />)
    open()
    const src = frames()[0]!.getAttribute('src')!
    expect(src).not.toContain('?surface=')
    expect(src).not.toContain('surface-token')
    expect(src.split('?')[1]).toBeUndefined()
    expect(src).not.toContain('#')
  })

  /// One opened surface costs the mount document plus whatever the plugin's own
  /// entry references; the host adds none of its own. Measured with the fixture
  /// #42 serves (`ui/index.html` + one `<script src="app.js">`): two requests.
  it('asks for nothing beyond the surface itself', () => {
    const fetchSpy = vi.fn()
    const xhrSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    vi.stubGlobal('XMLHttpRequest', function XHR() {
      xhrSpy()
    })
    render(<OverlayHost />)
    open('a')
    open('b')
    const urlBearing = Array.from(document.querySelectorAll('[src], [href]')).map(
      (el) => el.tagName,
    )
    expect(urlBearing).toEqual(['IFRAME', 'IFRAME'])
    expect(frames().map((f) => f.getAttribute('src'))).toEqual([
      'http://127.0.0.1:8765/api/plugins/ui/a/n0nce/',
      'http://127.0.0.1:8765/api/plugins/ui/b/n0nce/',
    ])
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(xhrSpy).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('stops sending for the surface the user closed', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0]!)
    expect(frames()).toHaveLength(1)
    expect(frames()[0]!.getAttribute('src')).toBe('http://127.0.0.1:8765/api/plugins/ui/b/n0nce/')
  })
})

describe('the box order comes from the model', () => {
  it('paints bottom-up by z, even when the store array says otherwise', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    act(() => useChatStore.getState().focusOverlay(surfaceKey('a')))
    expect(zOf('a')).toBeGreaterThan(zOf('b'))
    expect(useChatStore.getState().overlay.surfaces.map((s) => s.pluginId)).toEqual(['a', 'b'])
    expect(boxes().map((b) => b.getAttribute('data-plugin'))).toEqual(['b', 'a'])
    expect(rankOf(boxes()[0])).toBe('0')
    expect(rankOf(boxes()[1])).toBe('1')
  })

  /// The rank is the only lever the sheet is given: the sheet adds it to the
  /// overlay step, so the stack stays under the app's own modals. A component that
  /// improvised a z-index here would sit above them and outside the sheet's rule.
  it('hands the sheet a rank and keeps z-index out of the inline style', () => {
    render(<OverlayHost />)
    open()
    const style = boxes()[0]!.getAttribute('style')!
    expect(style).not.toContain('z-index')
    expect(style).toContain('--stack-rank: 0')
    expect(css).toMatch(/z-index:\s*calc\(var\(--z-index-overlay\)\s*\+\s*var\(--stack-rank/)
  })

  it('restores through the model: the surface returns on top and inside the window', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    const before = zOf('a')
    // Bottom-up render order: `a` is the first box, so its rail is the first control.
    fireEvent.keyDown(screen.getAllByRole('button', { name: 'Minimize' })[0]!, { key: 'Escape' })
    expect(zOf('a')).toBe(before)
    act(() => useChatStore.getState().focusOverlay(surfaceKey('b')))
    fireEvent.click(screen.getByRole('button', { name: 'Maximize' }))
    expect(zOf('a')).toBeGreaterThan(zOf('b'))
    expect(useChatStore.getState().overlay.topZ).toBe(zOf('a'))
    expect(boxes().map((b) => b.getAttribute('data-plugin'))).toEqual(['b', 'a'])
    expect(document.querySelector('[data-testid="overlay-frame-a"]')?.hasAttribute('hidden')).toBe(
      false,
    )
  })

  it('raises what the pointer lands on and leaves the other rank alone', () => {
    render(<OverlayHost />)
    open('a')
    open('b')
    fireEvent.pointerDown(boxes()[1]!, { pointerId: 9, clientX: 10, clientY: 10, button: 0 })
    expect(zOf('b')).toBeGreaterThan(zOf('a'))
    expect(rankOf(boxes()[1])).toBe('1')
    expect(rankOf(boxes()[0])).toBe('0')
  })
})

describe('the numbers this component writes itself', () => {
  it('names the surface the descriptor gave, or the plugin when it gave nothing', () => {
    render(<OverlayHost />)
    open('acme-no-title', { title: '' })
    expect(screen.getByRole('region', { name: 'acme-no-title' })).toBeTruthy()
    expect(frames()[0]!.getAttribute('title')).toBe('acme-no-title')
    expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual([
      'Reload',
      'Minimize',
      'Close',
      'Resize surface',
    ])
  })

  /// A minimized surface is one rail: the row that stays on screen has to stay
  /// grabbable at the touch floor, and it is the only height written inline.
  it('paints a minimized surface exactly one rail tall', () => {
    render(<OverlayHost />)
    open()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Minimize' }), { key: 'Escape' })
    const style = boxes()[0]!.getAttribute('style')!
    expect(OVERLAY_RAIL_HEIGHT).toBe(44)
    expect(style).toContain(`height: ${OVERLAY_RAIL_HEIGHT}px`)
    expect(style).toContain('width: 360px')
    expect(boxes()[0]!.getAttribute('data-minimized')).toBe('true')
  })

  /// The sheet and the model state the same floor twice; derive one from the other
  /// so a change to either that leaves the row under the touch target fails here.
  it('holds one 44 px floor across the sheet and the model', () => {
    const rail = css.match(/\.overlay-rail\s*\{[^}]*height:\s*(\d+)px/)
    const control = css.match(/\.overlay-control\s*\{[^}]*width:\s*(\d+)px/)
    const controlHeight = css.match(/\.overlay-control\s*\{[^}]*height:\s*(\d+)px/)
    expect(rail?.[1]).toBe(String(OVERLAY_RAIL_HEIGHT))
    expect(control?.[1]).toBe('44')
    expect(controlHeight?.[1]).toBe('44')
    expect(css).toMatch(/\.overlay-frame\s*\{[^}]*height:\s*calc\(100% - 44px\)/)
  })

  it('keeps the frame mounted while minimized, hidden only from the paint', () => {
    render(<OverlayHost />)
    open()
    const src = frames()[0]!.getAttribute('src')
    fireEvent.click(screen.getByRole('button', { name: 'Minimize' }))
    expect(frames()).toHaveLength(1)
    expect(frames()[0]!.getAttribute('src')).toBe(src)
    expect(frames()[0]!.hasAttribute('hidden')).toBe(true)
    expect(boxes()[0]!.getAttribute('style')).toContain(`height: ${OVERLAY_RAIL_HEIGHT}px`)
  })

  it('answers Escape on the surface, and only minimizes', () => {
    render(<OverlayHost />)
    open()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Close' }), { key: 'Escape' })
    expect(useChatStore.getState().overlay.surfaces).toHaveLength(1)
    expect(useChatStore.getState().overlay.surfaces[0]?.minimized).toBe(true)
    expect(document.activeElement?.getAttribute('aria-label')).toBe('Maximize')
    expect(screen.getByRole('button', { name: 'Close' })).toBeTruthy()
  })
})
