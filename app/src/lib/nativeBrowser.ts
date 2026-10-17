'use client'

/**
 * W1: the native browser bridge.
 *
 * The URL pane used to be an `<iframe>`. Pages with `X-Frame-Options` /
 * `frame-ancestors` (google.com, github.com, …) paint a white box inside it —
 * measured 2026-10-06: `https://google.com` → the frame reports "finished",
 * region 419×646 px, content empty. The Tauri shell has a real engine:
 * `browser_open` (src-tauri/src/browser.rs) places the page as a child WebView
 * over the frame area. A child WebView knows no CSS, so the frontend reports
 * its own geometry (bounds) and hides the surface as long as an overlay would
 * lie on top of it.
 *
 * The PWA has no such path — there the iframe stays with its
 * honest notice. `hasNativeBrowser()` is the only difference
 * the surface has to know.
 */
import { isExternalHttpUrl } from '@/components/dashboard/agent/previewUrl'

export type BrowserBounds = { x: number; y: number; width: number; height: number }

export type BrowserEvent =
  | { kind: 'navigation'; url: string }
  | { kind: 'load'; phase: 'started' | 'finished'; url: string }
  | { kind: 'title'; title: string }
  | { kind: 'new-window'; url: string }

type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
type Listen = (event: string, handler: (e: { payload: unknown }) => void) => Promise<() => void>
type TauriBridge = { core: Invoke; listen: Listen }

function bridge(): TauriBridge | null {
  if (typeof window === 'undefined') return null
  // @tauri-apps/api is not a dependency of this project — the globally
  // injected bridge (withGlobalTauri) is the only way into the shell.
  const tauri = (
    window as unknown as {
      __TAURI__?: { core?: { invoke?: unknown }; event?: { listen?: unknown } }
    }
  ).__TAURI__
  const core = tauri?.core?.invoke
  const listen = tauri?.event?.listen
  if (typeof core !== 'function' || typeof listen !== 'function') return null
  return { core: core as Invoke, listen: listen as Listen }
}

/** Only the desktop has a real engine behind the pane. */
export const hasNativeBrowser = (): boolean => bridge() !== null

/**
 * The pane takes natively what the iframe cannot: everything except loopback.
 * The loopback path (dev server with HMR, `proxyFetch` for LAN) stays
 * as it is — it works and was never reported as broken.
 */
export function usesNativeBrowser(url: string): boolean {
  if (!hasNativeBrowser()) return false
  if (!isExternalHttpUrl(url)) return false
  return !/^https?:\/\/(localhost|127\.0\.0\.1|\[::1])(?::\d{1,5})?(?:\/|$)/i.test(url)
}

export async function openNativeBrowser(url: string, bounds: BrowserBounds): Promise<void> {
  await bridge()?.core('browser_open', { url, bounds })
}

export async function setNativeBrowserBounds(bounds: BrowserBounds): Promise<void> {
  await bridge()?.core('browser_bounds', { bounds })
}

export async function setNativeBrowserVisible(visible: boolean): Promise<void> {
  await bridge()?.core('browser_visible', { visible })
}

export async function nativeBrowserHistory(action: 'back' | 'forward' | 'reload'): Promise<void> {
  await bridge()?.core('browser_history', { action })
}

export async function closeNativeBrowser(): Promise<void> {
  await bridge()?.core('browser_close')
}

/**
 * "Open in browser": inside the shell `window.open` leads nowhere (no way
 * outside), hence the detour over the operating system. Without a shell (PWA)
 * `window.open` is exactly right.
 */
export async function openExternally(url: string): Promise<void> {
  const b = bridge()
  if (!b) {
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  await b.core('browser_open_external', { url })
}

const EVENTS: { name: string; map: (p: Record<string, unknown>) => BrowserEvent }[] = [
  { name: 'browser:navigation', map: (p) => ({ kind: 'navigation', url: String(p.url ?? '') }) },
  {
    name: 'browser:load',
    map: (p) => ({
      kind: 'load',
      phase: p.phase === 'started' ? 'started' : 'finished',
      url: String(p.url ?? ''),
    }),
  },
  { name: 'browser:title', map: (p) => ({ kind: 'title', title: String(p.title ?? '') }) },
  { name: 'browser:new-window', map: (p) => ({ kind: 'new-window', url: String(p.url ?? '') }) },
]

/** Subscription to every pane event; returns the cleanup function. */
export function listenNativeBrowser(onEvent: (e: BrowserEvent) => void): () => void {
  const b = bridge()
  if (!b) return () => {}
  let dead = false
  const unlisten: (() => void)[] = []
  for (const spec of EVENTS) {
    void b
      .listen(spec.name, (e) => {
        if (dead) return
        onEvent(spec.map((e.payload ?? {}) as Record<string, unknown>))
      })
      .then((fn) => {
        if (dead) fn()
        else unlisten.push(fn)
      })
      .catch(() => {
        /* without an event channel the pane keeps its loading state */
      })
  }
  return () => {
    dead = true
    unlisten.forEach((fn) => fn())
  }
}
