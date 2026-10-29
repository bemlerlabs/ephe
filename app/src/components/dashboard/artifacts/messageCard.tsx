/**
 * Ephe — a file the turn produced, reachable in the message that produced it.
 *
 * A run announces a file in three ways (`file_result` leaves an activity with a
 * path, the detector leaves an artifact without content, a tool call may name the
 * path in its args) and only the last one ever had a click target. This card reads
 * the first two off the message and gives them the same gesture the workbench row
 * has. It stays outside the collapsed timeline on purpose: the file is the result
 * of the turn, and the turn's steps are what collapse.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  AlertTriangle,
  Check,
  Download,
  FileCode,
  FileText,
  FolderDown,
  Image as ImageIcon,
  X,
} from 'lucide-react'
import { ApiError, artifactFileUrl, fileUrl } from '@/lib/api'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { ContentPreview } from './preview'
import {
  artifactPreviewMode,
  previewSandbox,
  previewShowsInFrame,
  previewSrc,
} from '@/lib/previewMode'
import type { ChatMessage } from '@/types'
import { adoptWithTarget } from './adoptFlow'

export interface ProducedFile {
  key: string
  name: string
  path: string
  kind: string
  /** Set when the workbench registered the bytes — adopt needs it, open does not. */
  artifactId?: string
}

function nameOf(p: string): string {
  return p.split('/').filter(Boolean).pop() ?? p
}

/** The files this message produced, in the order they arrived, without repeats. */
export function producedFiles(m: ChatMessage): ProducedFile[] {
  const out: ProducedFile[] = []
  const seen = new Set<string>()
  for (const a of m.activities ?? []) {
    if (!a.path || seen.has(a.path)) continue
    seen.add(a.path)
    out.push({
      key: `act-${a.id}`,
      name: nameOf(a.path),
      path: a.path,
      kind: a.fileType ?? '',
      artifactId: a.artifactId,
    })
  }
  // An artifact WITH content is a code block and stays one. Without content it is
  // bytes the chat cannot show, and a filename is all the message carries.
  for (const art of m.artifacts ?? []) {
    if (art.content || !art.filename || seen.has(art.filename)) continue
    seen.add(art.filename)
    out.push({
      key: `art-${art.id}`,
      name: nameOf(art.filename),
      path: art.filename,
      kind: art.artifact_type ?? '',
    })
  }
  return out
}

function CardIcon({ mode }: { mode: string }) {
  if (mode === 'image' || mode === 'audio' || mode === 'video')
    return <ImageIcon className="h-3.5 w-3.5 text-brand/70" />
  if (mode === 'frame') return <FileText className="h-3.5 w-3.5 text-brand/70" />
  return <FileCode className="h-3.5 w-3.5 text-brand/70" />
}

export default function MessageFileCard({ file }: { file: ProducedFile }) {
  const { t } = useTranslation()
  const [phase, setPhase] = useState<'idle' | 'busy' | 'done' | 'failed'>('idle')
  const [broken, setBroken] = useState(false)
  const [reason, setReason] = useState('')
  const [retry, setRetry] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const mode = artifactPreviewMode(file.name, file.kind)
  // The pane shows a frame for whatever the browser can present. A PDF on the
  // desktop shell has no viewer in a frame (measured 2026-10-07, recorded in
  // previewMode), and 'none' is a format nothing renders at all — offering open
  // there would deliver a white box or a download the user did not ask for.
  const openable = mode !== 'none' && previewShowsInFrame(file.name, file.kind)
  const view = fileUrl(file.path)
  const bytes = file.artifactId ? artifactFileUrl(file.artifactId) : view
  const src = retry ? `${bytes}${bytes.includes('?') ? '&' : '?'}retry=${retry}` : bytes
  const inline =
    (openable && (mode === 'image' || mode === 'frame' || mode === 'video' || mode === 'audio')) ||
    (mode === 'content' && !!file.artifactId)

  function failed(why = '') {
    setBroken(true)
    setReason(why)
  }

  /* An <img> reports failure without a status. One small request tells why, so
     the card names the cause instead of repeating its own label. */
  async function unreadableReason(url: string): Promise<string> {
    try {
      const res = await fetch(url, { headers: { Range: 'bytes=0-0' } })
      if (res.ok) return ''
      if (res.status === 403) return t('artifacts.reasonProtected')
      if (res.status === 404) return t('artifacts.reasonMissing')
      return String(res.status)
    } catch {
      return t('artifacts.reasonOffline')
    }
  }

  function tryAgain() {
    setBroken(false)
    setReason('')
    setRetry((value) => value + 1)
  }

  async function adopt() {
    if (!file.artifactId) return
    setPhase('busy')
    try {
      await adoptWithTarget(file.artifactId, file.name, t('artifacts.adopt'))
      setPhase('done')
    } catch (e) {
      // 422 asks where the copy should go; the answer already went through the
      // dialog above, so here it means the server forgot the target.
      if (e instanceof ApiError && e.status === 422) {
        setPhase('idle')
        return
      }
      setPhase('failed')
    }
  }

  return (
    <>
      {inline && broken && (
        <div
          role="alert"
          data-testid={`message-file-unavailable-${file.key}`}
          className="mt-2 flex items-center gap-2 rounded-md border border-status-warning/40 bg-status-warning/10 px-2 py-1.5 text-ui-xs text-foreground/85"
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-status-warning" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            {t(mode === 'image' ? 'artifacts.imageUnavailable' : 'artifacts.mediaUnavailable')}
            {reason ? ` — ${reason}` : ''}
          </span>
          <button
            type="button"
            onClick={tryAgain}
            data-testid={`message-file-retry-${file.key}`}
            className="shrink-0 rounded px-1.5 py-0.5 text-ui-2xs font-medium text-brand-deep hover:bg-brand/10"
          >
            {t('artifacts.previewRetry')}
          </button>
        </div>
      )}
      {inline && !broken && mode === 'content' && file.artifactId && (
        <div
          data-testid={`message-file-content-${file.key}`}
          className="mt-2 max-h-72 overflow-auto rounded-md border border-hairline bg-surface/40"
        >
          <ContentPreview art={{ id: file.artifactId, version: 0, name: file.name }} />
        </div>
      )}
      {inline && !broken && mode === 'image' && (
        <button
          type="button"
          onClick={() => setLightbox(true)}
          aria-label={`${file.name}: ${t('artifacts.previewOpen')}`}
          data-testid={`message-file-image-${file.key}`}
          className="mt-2 block max-w-full rounded-md border border-hairline bg-surface/40 p-1"
        >
          <img
            src={src}
            alt={file.name}
            onError={() => {
              void unreadableReason(src).then(failed)
            }}
            className="max-h-72 max-w-full object-contain"
          />
        </button>
      )}
      {inline && !broken && mode === 'video' && (
        <video
          controls
          preload="metadata"
          src={src}
          onError={() => {
            void unreadableReason(src).then(failed)
          }}
          data-testid={`message-file-video-${file.key}`}
          className="mt-2 max-h-72 w-full rounded-md border border-hairline bg-black"
        />
      )}
      {inline && !broken && mode === 'audio' && (
        <audio
          controls
          preload="metadata"
          src={src}
          onError={() => {
            void unreadableReason(src).then(failed)
          }}
          data-testid={`message-file-audio-${file.key}`}
          className="mt-2 w-full"
        />
      )}
      {inline && !broken && mode === 'frame' && (
        <iframe
          src={previewSrc(src, file.name, file.kind)}
          sandbox={previewSandbox(file.name, file.kind)}
          title={file.name}
          data-testid={`message-file-frame-${file.key}`}
          className="mt-2 h-72 w-full rounded-md border border-hairline bg-white"
        />
      )}
      <div
        data-testid={`message-file-${file.key}`}
        className="mt-2 flex items-center gap-2 rounded-md border border-hairline bg-surface/60 px-2 py-1.5"
      >
        <CardIcon mode={mode} />
        <span className="min-w-0 flex-1 truncate text-ui-xs text-foreground/85" title={file.path}>
          {file.name}
        </span>
        {phase === 'failed' && (
          <>
            <span role="alert" className="text-ui-2xs text-destructive">
              {t('artifacts.adoptFailed')}
            </span>
            <button
              type="button"
              onClick={() => void adopt()}
              data-testid={`message-file-adopt-retry-${file.key}`}
              className="shrink-0 rounded px-1 py-0.5 text-ui-2xs font-medium text-brand-deep transition-colors hover:bg-brand/10"
            >
              {t('agentPanel.retry')}
            </button>
          </>
        )}
        {openable && (
          <button
            type="button"
            data-testid={`message-file-open-${file.key}`}
            aria-label={`${t('chat.openInPanel')}: ${file.name}`}
            title={t('chat.openInPanel')}
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'preview', url: view } }),
              )
            }
            className="rounded-md px-1.5 py-1 text-ui-2xs font-medium text-brand-deep hover:bg-brand/10 transition-colors"
          >
            {t('chat.openInPanel')}
          </button>
        )}
        {!openable && mode === 'frame' && (
          <span className="text-ui-2xs text-ink-faint">{t('artifacts.preview.noViewer')}</span>
        )}
        {file.artifactId ? (
          <button
            type="button"
            disabled={phase === 'busy' || phase === 'done'}
            data-testid={`message-file-adopt-${file.key}`}
            aria-label={`${t('artifacts.adopt')}: ${file.name}`}
            title={t('artifacts.adoptHint')}
            onClick={() => void adopt()}
            className="flex shrink-0 items-center gap-1 rounded px-1.5 py-1 min-h-7 max-lg:min-h-11 text-ui-2xs font-medium text-ink-soft hover:text-foreground hover:bg-surface disabled:opacity-50"
          >
            {phase === 'done' ? (
              <Check className="h-3.5 w-3.5 text-status-success" />
            ) : (
              <FolderDown className="h-3.5 w-3.5" />
            )}
            <span>{t('artifacts.adopt')}</span>
          </button>
        ) : null}
        <a
          href={file.artifactId ? artifactFileUrl(file.artifactId, true) : view}
          download={file.name}
          aria-label={`${t('artifacts.download')}: ${file.name}`}
          title={t('artifacts.downloadHint')}
          data-testid={`message-file-download-${file.key}`}
          className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 shrink-0 rounded hover:bg-surface text-ink-soft hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" />
        </a>
      </div>
      {lightbox && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={file.name}
          onClick={() => setLightbox(false)}
          data-testid={`message-file-lightbox-${file.key}`}
          className="fixed inset-0 z-50 flex items-center justify-center bg-surface/95 p-4"
        >
          <img src={src} alt={file.name} className="max-h-full max-w-full object-contain" />
          <button
            type="button"
            onClick={() => setLightbox(false)}
            aria-label={t('artifacts.lightboxClose')}
            className="absolute right-4 top-4 rounded-full bg-surface/90 p-2 text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      )}
    </>
  )
}
