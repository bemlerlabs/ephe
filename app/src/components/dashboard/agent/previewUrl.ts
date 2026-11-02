/** The pure side of the browser pane: URL normalisation and the reporting deadline. */

/** P6 B5 (ref-22/24): one pane for internal AND external URLs. */
export const isExternalHttpUrl = (u: string) => /^https?:\/\//i.test(u)

/** A file the workspace holds, served by the backend's own file endpoint. */
const FILE_ENDPOINT = /^\/api\/file\?/i

/** This machine's own server: a dev server the run started, the PWA itself.
 *  `previewTab.tsx` keeps its own loopback read because it needs the port as a
 *  capture for the proxy path; this one only decides which chrome to draw. */
const LOOPBACK_URL = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?([/?#]|$)/i

/**
 * A1: what the one pane is actually showing. A document, a site this machine
 * runs and a page on the internet arrive through the same address bar today, so
 * opening a contract reads like opening a website — reload, back and forward
 * mean nothing for a file, and the reader is left holding a browser chrome
 * around a document.
 */
export type PaneMode = 'document' | 'site' | 'web'

export function paneMode(url: string): PaneMode {
  const value = (url ?? '').trim()
  if (FILE_ENDPOINT.test(value)) return 'document'
  if (LOOPBACK_URL.test(value)) return 'site'
  return 'web'
}

/** Supply the scheme for scheme-less input ("example.com" → https://example.com). */
export function normalizeBrowserUrl(raw: string): string {
  const v = raw.trim()
  if (!v) return ''
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(v)) return v
  if (/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?([/?#].*)?$/i.test(v)) return `http://${v}`
  return `https://${v}`
}

/**
 * G3: from when a missing load event is reported as "slow". Cross-origin the
 * frame can read neither an error nor progress — so the row must not state a
 * guess before this deadline has passed.
 */
export const FRAME_SLOW_MS = 8000
