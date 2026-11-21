/**
 * The one way a page inside Ephe reaches a page outside it.
 *
 * `nativeBrowser.ts` owns the pane — the child WebView that paints a site inside the
 * window. This module owns the other half: handing an address to the operating system.
 * It is separate because the surfaces that only need to leave (a documentation link, a
 * release page, an installer download) must not carry the pane's bounds, history and
 * event machinery with them; measured 2026-11-02, importing the pane module pulled
 * `browser_bounds`, `browser_visible` and `browser_history` into the shared `ui` chunk
 * for the sake of one click, and the chunk went from 15.09 kB to 17.6 kB gzip.
 *
 * Inside the shell `window.open` is no way out — the call goes through the injected
 * bridge to `browser_open_external` (src-tauri/src/browser.rs:188, which opens only
 * http and https). Without a shell, in a browser tab, `window.open` is exactly right.
 */
type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
type Listen = (event: string, handler: (e: { payload: unknown }) => void) => Promise<() => void>

/** The globally injected bridge (`withGlobalTauri`); `@tauri-apps/api` is not a dependency. */
export function bridge(): { core: Invoke; listen?: Listen } | null {
  if (typeof window === 'undefined') return null
  const tauri = (
    window as unknown as {
      __TAURI__?: { core?: { invoke?: unknown }; event?: { listen?: unknown } }
    }
  ).__TAURI__
  const core = tauri?.core?.invoke
  const listen = tauri?.event?.listen
  if (typeof core !== 'function') return null
  return {
    core: core as Invoke,
    listen: typeof listen === 'function' ? (listen as Listen) : undefined,
  }
}

/** Only the desktop has a shell behind the page. */
export const inShell = (): boolean => bridge() !== null

export async function openExternally(url: string): Promise<void> {
  const b = bridge()
  if (!b) {
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  await b.core('browser_open_external', { url })
}

/**
 * One document-level delegate, installed by the entry, so no surface can forget the way out.
 *
 * Measured 2026-11-02: eleven blank-target anchors across the marketplace detail, the setup
 * page and the update dialog did nothing in the shell, because a new-window request has no
 * window there. A component per link would have fixed those eleven and left the twelfth to be
 * discovered by a reader; and it joined the eager `ui` chunk (15.09 kB measured at its row,
 * 17.16 kB with the door in it) to hand over one URL. Here the plain anchor stays plain —
 * keyboard, focus, copy-address and a browser tab are untouched — and only a plain left click
 * on a cross-origin address in the shell is turned into the operating system's own browser.
 */
export function installExternalLinks(): void {
  document.addEventListener('click', (event) => {
    if (
      !inShell() ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return
    const anchor = (event.target as Element | null)?.closest?.(
      'a[href]',
    ) as HTMLAnchorElement | null
    if (!anchor || anchor.target !== '_blank') return
    const url = anchor.href
    if (!leavesTheApp(url)) return
    event.preventDefault()
    void openExternally(url)
  })
}

/** The app's own origin is not a way out; everything else http(s) is. */
function leavesTheApp(url: string): boolean {
  try {
    const target = new URL(url)
    if (target.protocol !== 'http:' && target.protocol !== 'https:') return false
    return target.origin !== window.location.origin
  } catch {
    return false
  }
}
