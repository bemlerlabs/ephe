'use client'

/**
 * W1: the native browser bridge.
 *
 * The URL pane used to be an `<iframe>`. Pages that send `X-Frame-Options` /
 * `frame-ancestors` paint a white box inside it — measured 2026-10-06: a public
 * search site → the frame reports "finished", region 419×646 px, content empty.
 * The Tauri shell has a real engine:
 * `browser_open` (src-tauri/src/browser.rs) places the page as a child WebView
 * over the frame area. A child WebView knows no CSS, so the frontend reports
 * its own geometry (bounds) and hides the surface as long as an overlay would
 * lie on top of it.
 *
 * The PWA has no such path — there the iframe stays with its
 * honest notice. `hasNativeBrowser()` is the only difference
 * the surface has to know.
 *
 * The pane loads pages nobody here wrote, so `browser.rs` keeps them out of the
 * schemes that are not the web (`file:`, the shell's own handlers) and reports a
 * refusal instead of cancelling silently. `refused` is that report; the shell
 * ships a code, the wording is this side's to choose.
 */
import { isExternalHttpUrl, paneMode } from '@/components/dashboard/agent/previewUrl'
import { bridge } from './openExternal'

export type BrowserBounds = { x: number; y: number; width: number; height: number }

/** Why the pane would not take an address. Codes, not sentences — see `browser.rs`. */
export type BrowserRefusalReason = 'scheme-not-allowed' | 'app-own-origin'

/** An address the pane refused, with the scheme that decided it. */
export type BrowserRefusal = { url: string; scheme: string; reason: BrowserRefusalReason }

export type BrowserEvent =
  | { kind: 'navigation'; url: string }
  | { kind: 'load'; phase: 'started' | 'finished'; url: string }
  | { kind: 'title'; title: string }
  | { kind: 'new-window'; url: string }
  | ({ kind: 'refused' } & BrowserRefusal)

/** Only the desktop has a real engine behind the pane. */
export const hasNativeBrowser = (): boolean => bridge() !== null

/**
 * The pane takes natively what the iframe cannot: everything except loopback.
 * The loopback path (dev server with HMR, `proxyFetch` for LAN) stays
 * as it is — it works and was never reported as broken. "Which addresses are this
 * machine's own" is `previewUrl.ts`'s rule, the one the pane's chrome is drawn from
 * too — not a second copy of it here. The shell's allowlist (`browser.rs`) reads
 * http/https and so permits these at the door; this surface still shows them in the
 * iframe.
 */
export function usesNativeBrowser(url: string): boolean {
  if (!hasNativeBrowser()) return false
  if (!isExternalHttpUrl(url)) return false
  return paneMode(url) === 'web'
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
 * Boot guard: the pane is a child WebView of the desktop window, and it paints above
 * this page. `browser.rs` hides it only from the page life that opened it, so a reload
 * while it was showing left the document it displayed floating over the chat with no
 * panel around it. A fresh load owns no pane, so the entry asks the shell once to close
 * whatever the previous page life left behind. In the PWA there is no shell and nothing to
 * close; a refusal is not the caller's to repair, so it is swallowed.
 */
export function closeOrphanedBrowserPane(): void {
  void closeNativeBrowser().catch(() => {
    /* no shell, or the shell refused: this page shows no pane either way */
  })
}

/**
 * "Open in browser" lives in `openExternal.ts`, beside the bridge it needs; the pane's
 * own calls stay here. Re-exported so every surface keeps one import path for the pane.
 */
export { openExternally } from './openExternal'

const REFUSAL_REASONS: BrowserRefusalReason[] = ['scheme-not-allowed', 'app-own-origin']

/** The code the shell sends, or the one a future shell adds — never a guess at prose. */
export function refusalReason(raw: unknown): BrowserRefusalReason {
  const value = String(raw ?? '')
  return REFUSAL_REASONS.find((reason) => reason === value) ?? 'scheme-not-allowed'
}

/**
 * The same code inside the command's own rejection.
 *
 * `browser_open` refuses at its door and answers its caller with a sentence that ends in
 * the code (`browser.rs`'s `refusal_message`). Reading the code out of it is what keeps
 * the shell's wording off a user surface: the pane has its own sentence for a refusal,
 * and the payload would otherwise be a string this project never wrote.
 */
export function refusalCode(message: string): BrowserRefusalReason | null {
  return REFUSAL_REASONS.find((reason) => message.includes(reason)) ?? null
}

/** The scheme of an address, for the sentence that names it. */
export function schemeOf(url: string): string {
  return (url.match(/^([a-z][a-z0-9+.-]*):/i)?.[1] ?? '').toLowerCase()
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
  {
    name: 'browser:refused',
    map: (p) => ({
      kind: 'refused',
      url: String(p.url ?? ''),
      scheme: String(p.scheme ?? ''),
      reason: refusalReason(p.reason),
    }),
  },
]

/** Subscription to every pane event; returns the cleanup function. */
export function listenNativeBrowser(onEvent: (e: BrowserEvent) => void): () => void {
  const listen = bridge()?.listen
  if (!listen) return () => {}
  let dead = false
  const unlisten: (() => void)[] = []
  for (const spec of EVENTS) {
    void listen(spec.name, (e) => {
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
