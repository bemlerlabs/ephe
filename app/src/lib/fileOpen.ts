import {
  AUDIO_EXT,
  extensionOf,
  FRAME_EXT,
  highlightLanguage,
  IMAGE_EXT,
  MARKDOWN_EXT,
  packedFormat,
  PLAIN_EXT,
  VIDEO_EXT,
} from './fileFormats'

/**
 * Ephe — one opener for every file a workspace holds.
 *
 * Two surfaces answer "what is this file": the artifact card (a file a tool produced,
 * reached through `/api/artifacts/<id>/file`) and the workspace column (a file that
 * simply exists, reached through `/api/file?path=`). The second one only knew Markdown,
 * code and plain text — `resolveFilePreview` returned null for a PNG and the Files tab
 * then handed the file to the browser pane, so a click on an image opened a URL bar.
 * The card already had answers for image, PDF, audio, video, spreadsheets, decks and the
 * honest "nothing here to show"; the column did not.
 *
 * This is the question both surfaces answer, in one place: given a name, what is it, and
 * what can this column do about it. Every branch has an answer, `binary` included — that
 * is a thing to say about the file, and the row keeps its gestures.
 */

/** A file that can be read as a page or as the text that made it. */
export type FileView = 'rendered' | 'source'

export type FileOpenPlan =
  /** Markdown: the words as a page, or as the source that made them. */
  | { kind: 'markdown'; views: readonly FileView[]; view: FileView }
  /** Source with highlighting; the language comes from the shared extension table. */
  | { kind: 'code'; language: string }
  /** Words with no grammar to highlight — a log, a CSV, a lock file. */
  | { kind: 'text' }
  | { kind: 'image' }
  | { kind: 'audio' }
  | { kind: 'video' }
  /** A page the viewer draws itself: PDF, or HTML with its own scripts. */
  | { kind: 'frame' }
  /** A container no viewer renders: xlsx, docx, pptx. The card asks the server about
   *  these; a loose workspace file has no server record to ask, so the column names the
   *  format and says where it can be read. */
  | { kind: 'packed'; format: 'table' | 'document' | 'deck' }
  /** Anything else: the bytes stay bytes, and the column says what it will do with them. */
  | { kind: 'binary' }

/** Markdown is the one format worth two views. */
const MARKDOWN_VIEWS = ['rendered', 'source'] as const

export function fileOpenPlan(name: string, kind = ''): FileOpenPlan {
  const ext = extensionOf(name, kind)
  if (IMAGE_EXT.has(ext)) return { kind: 'image' }
  if (AUDIO_EXT.has(ext)) return { kind: 'audio' }
  if (VIDEO_EXT.has(ext)) return { kind: 'video' }
  if (FRAME_EXT.has(ext)) return { kind: 'frame' }
  if (MARKDOWN_EXT.has(ext)) return { kind: 'markdown', views: MARKDOWN_VIEWS, view: 'rendered' }
  const language = highlightLanguage(name, kind)
  if (language) return { kind: 'code', language }
  const packed = packedFormat(name, kind)
  if (packed) return { kind: 'packed', format: packed }
  if (PLAIN_EXT.has(ext)) return { kind: 'text' }
  return { kind: 'binary' }
}

/** The view a file opens in, held only where the file has more than one. */
export function withFileView(plan: FileOpenPlan, view: FileView | null | undefined): FileOpenPlan {
  if (plan.kind !== 'markdown' || !view || !plan.views.includes(view)) return plan
  return { ...plan, view }
}

/** Does this plan read the bytes as text, or point a viewer at the address? */
export function fileIsText(plan: FileOpenPlan): boolean {
  return plan.kind === 'markdown' || plan.kind === 'code' || plan.kind === 'text'
}
