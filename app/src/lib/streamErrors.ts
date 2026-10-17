/**
 * Ephe — DD-15: human-readable stream errors instead of raw constructors.
 *
 * Root cause from the deep dive: once the backend was gone, `TypeError: Failed to
 * fetch` landed in the error bubble unfiltered and the header still read
 * "Connected". This pure function sorts network-like errors (the ones the browser
 * reports as a nameless TypeError) out before interpolation — the ChatLayout path
 * uses it before calling markStreamError.
 */
type Translator = (key: string, opts?: Record<string, unknown>) => string

// Same signature as the auto-retry gate in ChatLayout.runTurn — an error that counts
// as a network failure here is a stall-retry candidate there too.
const NETWORKISH =
  /connection|network|fetch|econn|enotfound|econnrefused|err_network|err_internet|load failed|failed to fetch/i

export function isNetworkLikeError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err ?? '')
  if (NETWORKISH.test(message)) return true
  // Browser-specific: WebKit throws "Load failed.", Gecko "NetworkError…".
  return err instanceof TypeError && message.length <= 60
}

export function humanizeStreamError(err: unknown, t: Translator): string {
  if (isNetworkLikeError(err)) return t('chat.offlineStreamError')
  let raw = err instanceof Error ? err.message : String(err ?? '')
  // String({}) yields "[object Object]" — raw constructors never get shown.
  if (!raw.trim() || /^\[object /i.test(raw)) raw = ''
  const message = raw.trim() || t('chat.streamErrorUnknown')
  return t('chat.streamError', { message })
}
