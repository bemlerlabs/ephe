/** The pure side of the browser pane: URL normalisation and the reporting deadline. */

/** P6 B5 (ref-22/24): one pane for internal AND external URLs. */
export const isExternalHttpUrl = (u: string) => /^https?:\/\//i.test(u)

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
