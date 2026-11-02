/**
 * Ephe — the extension tables, in one place.
 *
 * Three surfaces decide what a file is: the workspace column (`fileOpen`), the artifact
 * card (`previewMode`) and the browser pane's inline reader (`resolveFilePreview`). Each
 * used to carry its own list of suffixes, so a format could be known in one and unknown
 * in another — `.tsv` was `content` on a card and nothing at all in the pane, and the
 * reader fell back to a download for a file that is plain text.
 *
 * The lists live here now. What a surface *does* with a format stays its own business.
 */

export const MARKDOWN_EXT = new Set(['md', 'markdown'])

/** Suffixes with a grammar worth highlighting, and the name the highlighter answers to. */
export const CODE_EXT: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  rs: 'rust',
  go: 'go',
  java: 'java',
  json: 'json',
  yml: 'yaml',
  yaml: 'yaml',
  css: 'css',
  scss: 'scss',
  sql: 'sql',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  toml: 'toml',
  xml: 'xml',
  dockerfile: 'docker',
}

/** Words with no grammar to highlight. `tsv` and `env` belong here for the same reason
 *  `csv` does: the bytes are text, and a surface that treats them as an unknown binary
 *  offers a download for something a person meant to read. */
export const PLAIN_EXT = new Set(['txt', 'log', 'csv', 'tsv', 'ini', 'conf', 'env', 'lock'])

export const IMAGE_EXT = new Set(['svg', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'chart'])
export const FRAME_EXT = new Set(['pdf', 'html', 'htm'])
export const AUDIO_EXT = new Set(['mp3', 'wav', 'm4a', 'ogg', 'flac'])
export const VIDEO_EXT = new Set(['mp4', 'webm', 'mov'])

/** The office containers: a zip of parts, so no browser draws them and no reader in the
 *  column can. A server that unpacks them answers; the column asks or says it cannot. */
export const TABLE_EXT = new Set(['xlsx', 'xls'])
export const DOCUMENT_EXT = new Set(['docx'])
export const DECK_EXT = new Set(['pptx', 'ppt', 'odp'])

/** Everything the artifact surface is willing to ask the server about: the office
 *  containers, the documents it can read back as text, and the data files it can tabulate.
 *  Derived from the sets above so a format cannot be a text file in one surface and an
 *  unknown one in another. */
export const CONTENT_EXT = new Set([
  ...TABLE_EXT,
  ...DOCUMENT_EXT,
  ...DECK_EXT,
  ...MARKDOWN_EXT,
  ...PLAIN_EXT,
  'json',
  'yaml',
  'yml',
  'toml',
])

/** The suffix a name ends with, lowercased. A file without a dot (`ephe_chart`, a
 *  Dockerfile) has no extension in its name, so the kind the producer reported fills
 *  in — that is the answer, and a name is only a hint. */
export function extensionOf(name: string, kind = ''): string {
  const dot = (name ?? '').lastIndexOf('.')
  return (dot >= 0 ? name.slice(dot + 1) : (kind ?? '')).toLowerCase()
}

export function isImage(name: string, kind = ''): boolean {
  return IMAGE_EXT.has(extensionOf(name, kind))
}

export function packedFormat(name: string, kind = ''): 'table' | 'document' | 'deck' | null {
  const ext = extensionOf(name, kind)
  if (TABLE_EXT.has(ext)) return 'table'
  if (DOCUMENT_EXT.has(ext)) return 'document'
  if (DECK_EXT.has(ext)) return 'deck'
  return null
}

/** The highlight language for a name, or null when nothing knows its grammar. */
export function highlightLanguage(name: string, kind = ''): string | null {
  return CODE_EXT[extensionOf(name, kind)] ?? null
}
