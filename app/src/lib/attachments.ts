/**
 * G3 — attachment pipeline for the browser PWA (without Tauri).
 *
 * Images → Base64 data URL (for StreamChatRequest.images, the backend expects
 * bare Base64 values), text files → content with a 64 KB cap as a code block.
 */

/** Maximum text bytes taken from a file into the prompt. */
export const MAX_TEXT_ATTACHMENT_BYTES = 64 * 1024

interface AttachmentBase {
  path: string
  name: string
  /** Bytes as the picker reported them; absent for paths only (Tauri picker). */
  size?: number
  /** `loading` while the file is read, `error` when it could not be read. */
  status?: 'loading' | 'ready' | 'error'
}

export type ChatAttachment =
  | (AttachmentBase & { kind: 'image'; dataUrl: string })
  | (AttachmentBase & { kind: 'text'; text: string; truncated: boolean })
  | (AttachmentBase & { kind: 'file' })

/** Human size for the attachment card: B, KB, MB with one decimal. */
export function formatBytes(bytes: number | undefined): string {
  if (!bytes || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** File extension → Markdown language short name for the code block. */
const EXT_LANG: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  py: 'python',
  md: 'markdown',
  json: 'json',
  sh: 'bash',
  zsh: 'bash',
  yml: 'yaml',
  yaml: 'yaml',
  rs: 'rust',
  go: 'go',
  html: 'html',
  css: 'css',
  sql: 'sql',
  toml: 'toml',
}

export function isImageFile(f: File): boolean {
  return f.type.startsWith('image/')
}

/** Language from the file name (for the Markdown code block). */
export function langFor(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  return EXT_LANG[ext] ?? ''
}

/** Read an image as a Base64 data URL (preview + images parameter). */
export function readImageAsDataUrl(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(f)
  })
}

/** Read a text file with a 64 KB cap (above that, truncated=true). */
export function readTextAttachment(f: File): Promise<{ text: string; truncated: boolean }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const full = String(reader.result ?? '')
      if (full.length <= MAX_TEXT_ATTACHMENT_BYTES) {
        resolve({ text: full, truncated: false })
      } else {
        resolve({ text: full.slice(0, MAX_TEXT_ATTACHMENT_BYTES), truncated: true })
      }
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsText(f)
  })
}

/** File → ChatAttachment (image/text generically, binary as a pure path hint). */
export async function fileToAttachment(f: File): Promise<ChatAttachment> {
  const path = (f as File & { path?: string }).path || f.name
  if (isImageFile(f)) {
    return {
      kind: 'image',
      path,
      name: f.name,
      size: f.size,
      status: 'ready',
      dataUrl: await readImageAsDataUrl(f),
    }
  }
  if (f.type.startsWith('text/') || EXT_LANG[f.name.split('.').pop()?.toLowerCase() ?? '']) {
    const { text, truncated } = await readTextAttachment(f)
    return { kind: 'text', path, name: f.name, size: f.size, status: 'ready', text, truncated }
  }
  return { kind: 'file', path, name: f.name, size: f.size, status: 'ready' }
}

/**
 * Compose the payload text: message + text files as code blocks +
 * path hints for images/binary files (data URLs do NOT go into the text —
 * those travel via images).
 */
export function compositePayload(message: string, attachments: ChatAttachment[]): string {
  if (attachments.length === 0) return message
  const parts: string[] = [message]
  for (const a of attachments) {
    if (a.kind === 'text') {
      const lang = langFor(a.name)
      parts.push(
        `\n**${a.name}**${a.truncated ? ' (gekürzt)' : ''}:\n\`\`\`${lang}\n${a.text}\n\`\`\``,
      )
    } else {
      // A path that IS the name added nothing but a second copy of it.
      const hint = a.path && a.path !== a.name ? `${a.name} — ${a.path}` : a.name
      parts.push(`\n[Anhang: ${hint}]`)
    }
  }
  return parts.join('')
}

/** Image attachments only → bare Base64 values (without the data: prefix). */
export function compositeImages(attachments: ChatAttachment[]): string[] {
  return attachments
    .filter((a): a is Extract<ChatAttachment, { kind: 'image' }> => a.kind === 'image')
    .map((a) => a.dataUrl.split(',')[1] ?? '')
    .filter(Boolean)
}

/** Browser supports screen capture (desktop Chrome; mobile/iOS Safari: false). */
export function canCaptureScreen(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getDisplayMedia
}

/**
 * Desktop screenshot via getDisplayMedia: the browser shows its own permission
 * prompt, the user picks a screen/window and grants it themselves — no macOS
 * permission fiddling, no Tauri. The result runs through the same image pipeline
 * as an upload (fileToAttachment → images). User cancels → null.
 */
export async function captureScreenAsAttachment(): Promise<ChatAttachment | null> {
  if (!canCaptureScreen()) return null
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false })
  try {
    const track = stream.getVideoTracks()[0]
    if (!track) return null
    const video = document.createElement('video')
    video.srcObject = stream
    await video.play()
    // Pull one frame: video → canvas → PNG blob.
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d')?.drawImage(video, 0, 0)
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, 'image/png'))
    if (!blob) return null
    const file = new File([blob], `screenshot-${Date.now()}.png`, { type: 'image/png' })
    return await fileToAttachment(file)
  } finally {
    // Always stop the capture (turns the red recording bar off).
    stream.getTracks().forEach((t) => t.stop())
  }
}

/** What the shell's picker returns for a file it read. */
export interface PickedAttachment {
  name: string
  size: number
  kind: 'image' | 'text' | 'file'
  dataUrl?: string | null
  text?: string | null
  truncated?: boolean
}

/** The composer's shape for a file the shell read, with no path to carry. */
export function attachmentFromPick(picked: PickedAttachment): ChatAttachment {
  const base = {
    path: picked.name,
    name: picked.name,
    size: picked.size,
    status: 'ready' as const,
  }
  if (picked.kind === 'image' && picked.dataUrl) {
    return { ...base, kind: 'image', dataUrl: picked.dataUrl }
  }
  if (picked.kind === 'text' && picked.text != null) {
    return { ...base, kind: 'text', text: picked.text, truncated: Boolean(picked.truncated) }
  }
  return { ...base, kind: 'file' }
}
