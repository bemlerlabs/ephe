import i18n from '../i18n'

/**
 * The reader for a refusal that names its reason.
 *
 * A server that answers with a sentence answers in one language; the codes in
 * `server/refusals.py` are what lets this pick the reader's own instead. Unknown code, or a
 * bundle without the entry, returns the caller's fallback — the server's sentence — so a
 * missing translation costs a language, never a message.
 */
export function serverErrorText(
  code: string | undefined,
  params?: Record<string, string | number>,
  fallback = '',
): string {
  if (!code) return fallback
  const key = `serverError.${code}`
  if (!i18n.exists(key)) return fallback
  return String(i18n.t(key, { ...(params ?? {}), defaultValue: fallback }))
}
