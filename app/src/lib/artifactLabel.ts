import i18n from '../i18n'

/**
 * The card text for a file a turn produced, in the reader's language.
 *
 * The server says what a file *is* with `label_code` — the roles of the one WAV
 * marker are named once, in `core/artifact_markers.py` — and carries its own English
 * sentence in `label`. A code this bundle knows is read from the bundle under
 * `artifactLabel.`, with `{{name}}` for the file name; an unknown code, or a bundle
 * without the entry, keeps the server's sentence, so a missing translation costs a
 * language and never the card.
 */
export function artifactLabel(
  code: string | undefined,
  params?: Record<string, string | number>,
  fallback = '',
): string {
  if (!code) return fallback
  const key = `artifactLabel.${code}`
  if (!i18n.exists(key)) return fallback
  return String(i18n.t(key, { ...(params ?? {}), defaultValue: fallback }))
}

/** The file name a card carries: the last path segment the server sent. */
export function artifactName(path: string): string {
  return path.split('/').filter(Boolean).pop() ?? path
}
