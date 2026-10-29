import { IS_DESKTOP_SHELL } from './desktopBaseUrl'

/**
 * Ephe — DD-12: file preview in the agent panel without raw markup.
 *
 * The Files tab used to open every file as an iframe on /api/file?path=… —
 * a README appeared as an escaped wall of Markdown source and the address bar
 * showed the raw %2F query. These pure helpers decide the delivery (Markdown
 * render / code highlight / iframe) and the human-readable URL chip.
 */

const MARKDOWN_EXT = new Set(['md', 'markdown'])
const CODE_EXT: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  mjs: 'javascript',
  py: 'python',
  rs: 'rust',
  go: 'go',
  java: 'java',
  json: 'json',
  yml: 'yaml',
  yaml: 'yaml',
  css: 'css',
  sql: 'sql',
  sh: 'bash',
  toml: 'toml',
}
const PLAIN_EXT = new Set(['txt', 'log', 'csv', 'ini', 'conf'])

export type FilePreview =
  | { kind: 'markdown'; path: string; filename: string }
  | { kind: 'code'; path: string; filename: string; language: string }

/** Only the well-formed case: /api/file?path=<enc> as the single query argument.
 *  Everything else (HTML, images, foreign URLs, concatenated queries) is left to the iframe. */
export function resolveFilePreview(url: string): FilePreview | null {
  const m = /^\/api\/file\?path=([^&]+)$/.exec(url?.trim() ?? '')
  if (!m) return null
  let path: string
  try {
    path = decodeURIComponent(m[1] ?? '')
  } catch {
    return null
  }
  if (!path.startsWith('/')) return null
  const filename = path.split('/').pop() ?? ''
  const ext = (filename.split('.').pop() ?? '').toLowerCase()
  if (MARKDOWN_EXT.has(ext)) return { kind: 'markdown', path, filename }
  if (CODE_EXT[ext]) return { kind: 'code', path, filename, language: CODE_EXT[ext] }
  if (PLAIN_EXT.has(ext)) return { kind: 'code', path, filename, language: 'text' }
  return null
}

/** R4/A5: what an artifact card CAN show before it has loaded anything.
 *  'content' means: ask the server (table/text out of xlsx/docx) — a browser
 *  does not render that. 'code' means: the file endpoint serves the bytes as
 *  source, and the card shows them — code used to fall through to 'none'.
 *  'none' is an answer, not an error: the card then shows name, size and its
 *  gestures instead of an empty surface. */
export type ArtifactPreviewMode =
  'image' | 'frame' | 'audio' | 'video' | 'content' | 'code' | 'none'

const IMAGE_EXT = new Set(['svg', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'chart'])
const FRAME_EXT = new Set(['pdf', 'html', 'htm'])
const AUDIO_EXT = new Set(['mp3', 'wav', 'm4a', 'ogg', 'flac'])
const VIDEO_EXT = new Set(['mp4', 'webm', 'mov'])
const CONTENT_EXT = new Set([
  'xlsx',
  'xls',
  'csv',
  'docx',
  'pptx',
  'ppt',
  'odp',
  'md',
  'markdown',
  'txt',
  'log',
  'json',
  'yaml',
  'yml',
  'toml',
  'ini',
  'conf',
  'tsv',
])

export function artifactPreviewMode(name: string, kind = ''): ArtifactPreviewMode {
  // A file without a dot (ephe_chart) carries no extension in its name — then the
  // kind of the producing tool is a better answer than the name.
  const dot = name.lastIndexOf('.')
  const ext = (dot >= 0 ? name.slice(dot + 1) : (kind ?? '')).toLowerCase()
  if (IMAGE_EXT.has(ext)) return 'image'
  if (FRAME_EXT.has(ext)) return 'frame'
  if (AUDIO_EXT.has(ext)) return 'audio'
  if (VIDEO_EXT.has(ext)) return 'video'
  if (CONTENT_EXT.has(ext)) return 'content'
  // Code: the file endpoint serves the source, so the card shows it instead of
  // the 'unsupported' answer it gave for every .ts/.py/.sh before.
  if (CODE_EXT[ext]) return 'code'
  // The deck kinds go through the server's slide read; a deck it cannot parse
  // answers 'none' with a reason, and the card says that.
  return 'none'
}

/** Highlight language for a card the surface renders as source, else null.
 *  Same extension rule as artifactPreviewMode — the name's dot wins, the kind
 *  fills in for names without one. */
export function codePreviewLanguage(name: string, kind = ''): string | null {
  return CODE_EXT[extensionOf(name, kind)] ?? null
}

/** Sandbox frame for a preview — one rule, two surfaces.
 *
 * PDF is a dead format and its viewer is an extension in the browser. An
 * extension runs in **no** sandboxed frame — not even when you hand it its
 * origin back. Measured in real Chrome: `allow-popups` → sad document,
 * `allow-popups allow-same-origin` → sad document, no directive → the page.
 * So for PDF the directive stays away entirely, and the isolation is carried
 * by the answer itself (CSP `sandbox` on the file routes, server/middleware.py).
 *
 * Anything that can carry scripts (html, deck, svg, xml) keeps the frame
 * without origin — the second line of defence beside the answer.
 */
export function previewSandbox(name: string, kind = ''): string | undefined {
  return extensionOf(name, kind) === 'pdf' ? undefined : 'allow-popups'
}

/** What belongs in the frame. For PDF also the open parameters:
 *  without them the viewer shows the sheet at its last zoom level, and in a
 *  preview ~300 px tall that left a horizontally cropped strip (measured in the
 *  image). `view=FitH` fits the page to the frame width, `toolbar=0`/`navpanes=0`
 *  keep the tool row away — the gestures belong to the card, not to the viewer.
 *  A browser without these parameters ignores the fragment and still shows the sheet. */
export function previewSrc(url: string, name: string, kind = ''): string {
  const ext = extensionOf(name, kind)
  return ext === 'pdf' ? `${url}#toolbar=0&navpanes=0&view=FitH` : url
}

function extensionOf(name: string, kind: string): string {
  const dot = name.lastIndexOf('.')
  return (dot >= 0 ? name.slice(dot + 1) : (kind ?? '')).toLowerCase()
}

/** Can *this* surface show the format inside a frame?
 *
 * A PDF needs the browser's viewer. The desktop frame (WebKit) has none: the
 * same address, 200 and application/pdf, stays a white field there — measured on
 * the running window (2026-10-07, the desktop app's browser pane on exactly this
 * file). So a PDF on the desktop is not a preview but a card with an answer; in
 * the browser it stays a page. */
export function previewShowsInFrame(name: string, kind = '', desktop = IS_DESKTOP_SHELL): boolean {
  if (artifactPreviewMode(name, kind) !== 'frame') return true
  return !(desktop && extensionOf(name, kind) === 'pdf')
}

/** Chip text for the address bar: on the file endpoint the file name suffices
 *  (the %2F query is only noise for humans); normal URLs stay as they are. */ export function prettifyUrl(
  url: string,
): string {
  const preview = resolveFilePreview(url)
  if (preview) return preview.filename
  const m = /^\/api\/file\?path=([^&]+)$/.exec(url?.trim() ?? '')
  if (m) {
    try {
      return (
        decodeURIComponent(m[1] ?? '')
          .split('/')
          .pop() || url
      )
    } catch {
      return url
    }
  }
  return url
}

/** Highlight language for file contents (tool cards, write_file preview).
 *  Single source of the extension table: it stays with CODE_EXT/PLAIN_EXT here. */
export function fileLanguage(path: string): string {
  const filename = (path || '').split('/').pop() ?? ''
  const ext = (filename.split('.').pop() ?? '').toLowerCase()
  if (MARKDOWN_EXT.has(ext)) return 'markdown'
  const lang = CODE_EXT[ext]
  return lang ?? 'text'
}
