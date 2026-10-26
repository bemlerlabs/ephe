import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type Dispatch,
  type SetStateAction,
} from 'react'
import {
  attachmentFromPick,
  captureScreenAsAttachment,
  fileToAttachment,
  type ChatAttachment,
  type PickedAttachment,
} from '@/lib/attachments'
import { tauriInvoke } from '@/lib/tauriBridge'

/**
 * G3/P10-F1/P1-4: composer attachments — paste, drag & drop anywhere in the
 * viewport and the plus-menu file/image/screenshot handlers. The attachment
 * list itself stays with the caller (the send pipeline clears it); this hook
 * owns the mechanics (refs, drop depth, addFiles). Extracted from ChatInput.tsx.
 */
export function useComposerAttachments({
  setAttachments,
}: {
  setAttachments: Dispatch<SetStateAction<ChatAttachment[]>>
}) {
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  // G3: file selection — the Tauri native picker OR the browser file input.
  // `accept` restricts the choice (e.g. images only).
  // P10-F1 (round 14): paste a screenshot/image with Cmd+V straight into the
  // composer — same pipeline as drag & drop (addFiles). Standard pro flow.
  const handlePaste = (e: ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    const images: File[] = []
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile()
        if (file) images.push(file)
      }
    }
    if (images.length > 0) {
      e.preventDefault()
      const dt = new DataTransfer()
      images.forEach((f) => dt.items.add(f))
      void addFiles(dt.files)
    }
  }

  const addFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const list = Array.from(files)
    for (const f of list) {
      const placeholder: ChatAttachment = {
        kind: 'file',
        path: (f as File & { path?: string }).path || f.name,
        name: f.name,
        size: f.size,
        status: 'loading',
      }
      setAttachments((prev) => [...prev, placeholder])
      try {
        const ready = await fileToAttachment(f)
        setAttachments((prev) => prev.map((a) => (a === placeholder ? ready : a)))
      } catch {
        // The card says which file could not be read; the user can remove it.
        setAttachments((prev) =>
          prev.map((a) => (a === placeholder ? { ...placeholder, status: 'error' } : a)),
        )
      }
    }
  }

  // P1-4: full-surface drag and drop — files can be dropped ANYWHERE in the
  // viewport, not only on the composer zone. A window listener with a
  // dragenter/dragleave depth counter drives the overlay without flicker and hands
  // the drop to addFiles. The overlay has pointer-events:none so the drag events
  // pass through to the elements underneath (the counter stays correct).
  const addFilesRef = useRef(addFiles)
  useEffect(() => {
    addFilesRef.current = addFiles
  })
  useEffect(() => {
    const depth = { n: 0 }
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')
    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth.n += 1
      setDragOver(true)
    }
    const onOver = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
    }
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth.n = Math.max(0, depth.n - 1)
      if (depth.n === 0) setDragOver(false)
    }
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth.n = 0
      setDragOver(false)
      void addFilesRef.current(e.dataTransfer?.files ?? null)
    }
    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragover', onOver)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('drop', onDrop)
    }
  }, [])

  // Desktop: the shell's real «Open» dialog. PWA: the browser file input
  // (depending on accept) — that delivers the file itself, never a path.
  const handleAttach = async (accept?: string) => {
    const invoke = tauriInvoke()
    if (invoke) {
      try {
        const picked = (await invoke('pick_attachment', {
          accept: accept === 'image' ? 'image' : null,
        })) as PickedAttachment | null
        if (picked) setAttachments((prev) => [...prev, attachmentFromPick(picked)])
      } catch {
        // A cancelled dialog says nothing; a file the shell could not read is
        // reported by the command and leaves the composer untouched.
      }
      return
    }
    if (accept === 'image') {
      imageInputRef.current?.click()
    } else {
      fileInputRef.current?.click()
    }
  }

  // Desktop screenshot: browser prompt, the user grants it → attachment like an upload.
  const handleCaptureScreen = async () => {
    try {
      const att = await captureScreenAsAttachment()
      if (att) setAttachments((prev) => [...prev, att])
    } catch {
      // The user aborted the picker or did not allow capture → stay silent.
    }
  }

  return {
    dragOver,
    fileInputRef,
    imageInputRef,
    addFiles,
    handlePaste,
    handleAttach,
    handleCaptureScreen,
  }
}
