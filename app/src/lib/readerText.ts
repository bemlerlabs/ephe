type Translate = (key: string, options?: Record<string, unknown>) => unknown

/**
 * Resolves a tool result's reason code in the reader's language.
 *
 * The producer writes `reader.<code>` in both bundles (see `core/reason.py`).
 * A code without an entry, or no code at all, returns the caller's fallback —
 * the result's own first line — so a missing translation costs language, never
 * the reason itself. The caller's `t` is used instead of the i18n singleton:
 * a test that mocks the translation hook must not have to boot the instance.
 */
export function readerText(
  t: Translate,
  code: string | undefined,
  params?: Record<string, string | number>,
  fallback = '',
): string {
  if (!code) return fallback
  const key = `reader.${code}`
  const text = String(t(key, { ...(params ?? {}), defaultValue: key }))
  return text === key ? fallback : text
}
