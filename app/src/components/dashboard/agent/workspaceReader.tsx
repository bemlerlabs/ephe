'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ExternalLink,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  Pin,
  PinOff,
  RefreshCw,
} from 'lucide-react'
import { apiUrl } from '@/lib/api/http'
import { filePreviewByPath, type ArtifactContentPreview } from '@/lib/api'
import { LoadingRow } from '@/components/ui'
import { formatBytes } from '@/lib/dateLocale'
import {
  setWorkspaceFilePinned,
  setWorkspaceFileView,
  useWorkspaceFiles,
  type OpenFile,
} from '@/lib/workspaceFiles'
import {
  fileIsText,
  fileOpenPlan,
  withFileView,
  type FileOpenPlan,
  type FileView,
} from '@/lib/fileOpen'
import { previewSandbox, previewShowsInFrame, previewSrc } from '@/lib/previewMode'
import { PayloadView } from '@/components/dashboard/artifacts/preview'
import { FilePreviewBody } from './filePreview'

/**
 * Ephe — the workspace column's file reader (#111).
 *
 * The tree already knew every file in the folder; what it lacked was a place to put one.
 * A click handed the path to the browser pane, so a README arrived with an address bar and
 * a PNG arrived with a download. This is the other answer: the file opens in the column
 * that named it, under tabs a person can keep, in a view the format can actually hold.
 *
 * One question decides everything below — `fileOpenPlan` asks what the name is, and every
 * branch has an answer. A format this column cannot draw says so and hands over the
 * gesture that can reach it. That is the difference between a surface and an empty frame.
 */

export const workspaceFileUrl = (path: string): string =>
  `/api/file?path=${encodeURIComponent(path)}`

const STRIP_BUTTON =
  'inline-grid place-items-center p-1 min-h-6 rounded text-ink-faint hover:text-foreground hover:bg-surface-raised transition-colors shrink-0 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2'

/** Why the column shows no content, and the one gesture that still reaches the file. */
function FileHeld({
  file,
  plan,
  reason,
  onOpenInBrowser,
}: {
  file: OpenFile
  plan: FileOpenPlan
  reason: 'packed' | 'binary' | 'frame' | 'missing'
  onOpenInBrowser: (file: OpenFile) => void
}) {
  const { t } = useTranslation()
  const Icon =
    plan.kind === 'image'
      ? FileImage
      : plan.kind === 'audio'
        ? FileAudio
        : plan.kind === 'video'
          ? FileVideo
          : FileText
  const word =
    plan.kind === 'packed'
      ? t(
          plan.format === 'table'
            ? 'agentPanel.fileFormatTable'
            : plan.format === 'document'
              ? 'agentPanel.fileFormatDocument'
              : 'agentPanel.fileFormatDeck',
        )
      : ''
  const note =
    reason === 'missing'
      ? t('agentPanel.previewLoadFailed')
      : reason === 'frame'
        ? t('agentPanel.fileFrameNote')
        : reason === 'packed'
          ? t('agentPanel.filePackedNote', { format: word })
          : t('agentPanel.fileBinaryNote')
  return (
    <div
      data-testid="workspace-file-held"
      data-reason={reason}
      data-size={typeof file.size === 'number' ? file.size : undefined}
      className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-ui-xs text-ink-soft"
    >
      <Icon className="h-9 w-9 opacity-40 text-ink-faint" aria-hidden="true" />
      <span className="break-all font-medium text-foreground/80">{file.name}</span>
      <span className="max-w-72">{note}</span>
      {typeof file.size === 'number' && file.size > 0 && (
        <span className="font-mono text-ui-2xs text-ink-faint">{formatBytes(file.size)}</span>
      )}
      <button
        type="button"
        onClick={() => onOpenInBrowser(file)}
        className="mt-1 inline-flex min-h-7 items-center gap-1.5 rounded-md border border-hairline px-2.5 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground focus-ring"
      >
        <ExternalLink className="h-3 w-3" aria-hidden="true" />
        {t('agentPanel.openInPreview')}
      </button>
    </div>
  )
}

/** A packed office file, read by the server: rows, running text or slides.
 *
 * The column named these formats and stopped; a `.docx` click handed the person a download
 * because no browser draws a Word body, a deck or a sheet as content. The workbench card has
 * asked the server for exactly those three answers since R4/A5, so the column asks the same
 * question by path and shares the renderer. Where the server has nothing to show — a deck
 * with no text, a file the guard refuses, a sheet it cannot open — the held panel returns
 * with the gesture that still reaches the file, because a decline is an answer.
 */
function FileParsed({
  file,
  plan,
  nonce,
  onOpenInBrowser,
}: {
  file: OpenFile
  plan: FileOpenPlan
  nonce: number
  onOpenInBrowser: (file: OpenFile) => void
}) {
  const { t } = useTranslation()
  const [data, setData] = useState<ArtifactContentPreview | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setFailed(false)
    filePreviewByPath(file.path)
      .then((answer) => {
        if (!cancelled) setData(answer)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [file.path, nonce])

  if (failed || (data && data.mode === 'none')) {
    return <FileHeld file={file} plan={plan} reason="packed" onOpenInBrowser={onOpenInBrowser} />
  }
  if (!data) {
    return <LoadingRow label={t('artifacts.preview.loading')} className="h-full justify-center" />
  }
  return <PayloadView data={data} name={file.name} />
}

/** What a browser draws by itself: the media it plays, and the page a frame shows. */
function FileMedia({
  file,
  plan,
  nonce,
  onOpenInBrowser,
}: {
  file: OpenFile
  plan: FileOpenPlan
  nonce: number
  onOpenInBrowser: (file: OpenFile) => void
}) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [file.path, nonce])
  const src = apiUrl(workspaceFileUrl(file.path))
  if (failed) {
    return <FileHeld file={file} plan={plan} reason="missing" onOpenInBrowser={onOpenInBrowser} />
  }
  if (plan.kind === 'image') {
    return (
      <div className="flex h-full items-center justify-center overflow-auto bg-canvas/40 p-3">
        <img
          src={src}
          alt={file.name}
          onError={() => setFailed(true)}
          className="max-h-full max-w-full object-contain"
          data-testid="workspace-file-image"
        />
      </div>
    )
  }
  if (plan.kind === 'audio') {
    return (
      <div className="flex h-full items-center p-4">
        <audio controls src={src} onError={() => setFailed(true)} className="w-full" />
      </div>
    )
  }
  if (plan.kind === 'video') {
    return (
      <video
        controls
        src={src}
        onError={() => setFailed(true)}
        className="h-full w-full bg-canvas object-contain"
      />
    )
  }
  if (!previewShowsInFrame(file.name)) {
    // A PDF needs the browser's viewer and the desktop frame has none: the same
    // address there answers 200 with a white field, so the column says what it
    // cannot show instead of showing nothing.
    return <FileHeld file={file} plan={plan} reason="frame" onOpenInBrowser={onOpenInBrowser} />
  }
  return (
    <iframe
      // A dead format stays without the directive; anything that can carry scripts
      // keeps the frame without origin.
      sandbox={previewSandbox(file.name)}
      src={previewSrc(src, file.name)}
      title={file.name}
      style={{ colorScheme: 'light' }}
      className="h-full w-full bg-white"
      data-testid="workspace-file-frame"
    />
  )
}

/** One file: the line that names where it came from, the views it has, and the body. */
export function WorkspaceFileReader({
  file,
  onOpenInBrowser,
}: {
  file: OpenFile
  onOpenInBrowser: (file: OpenFile) => void
}) {
  const { t } = useTranslation()
  const { modes } = useWorkspaceFiles()
  const [nonce, setNonce] = useState(0)
  const plan = withFileView(fileOpenPlan(file.name), modes[file.path])
  const views: readonly FileView[] = plan.kind === 'markdown' ? plan.views : []
  const folder = file.path.slice(0, Math.max(0, file.path.length - file.name.length - 1))
  const reload = useCallback(() => setNonce((n) => n + 1), [])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-1.5 border-b border-hairline bg-surface px-3 py-1">
        <span
          className="min-w-0 flex-1 truncate font-mono text-ui-2xs text-ink-faint"
          title={file.path}
          data-testid="workspace-file-path"
        >
          {folder || file.path}
        </span>
        {views.length > 1 && (
          <div
            role="group"
            aria-label={t('agentPanel.fileViewGroup')}
            className="flex shrink-0 items-center gap-0.5 rounded-md border border-hairline p-0.5"
          >
            {views.map((view) => {
              const chosen = plan.kind === 'markdown' && plan.view === view
              return (
                <button
                  key={view}
                  type="button"
                  data-testid={`workspace-file-view-${view}`}
                  aria-pressed={chosen}
                  onClick={() => setWorkspaceFileView(file.path, view)}
                  className={`rounded px-1.5 py-0.5 text-ui-2xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring ${
                    chosen
                      ? 'bg-surface-raised text-foreground'
                      : 'text-ink-faint hover:text-foreground'
                  }`}
                >
                  {t(
                    view === 'rendered' ? 'agentPanel.fileViewPage' : 'agentPanel.fileViewMarkdown',
                  )}
                </button>
              )
            })}
          </div>
        )}
        <button
          type="button"
          data-testid="workspace-file-pin"
          onClick={() => setWorkspaceFilePinned(file.path, !file.pinned)}
          aria-pressed={file.pinned}
          aria-label={t(file.pinned ? 'agentPanel.fileReleaseTab' : 'agentPanel.fileKeepTab')}
          title={t(file.pinned ? 'agentPanel.fileReleaseTab' : 'agentPanel.fileKeepTab')}
          className={STRIP_BUTTON}
        >
          {file.pinned ? (
            <PinOff className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Pin className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          data-testid="workspace-file-reload"
          onClick={reload}
          aria-label={t('agentPanel.filesRefresh')}
          title={t('agentPanel.filesRefresh')}
          className={STRIP_BUTTON}
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
        </button>
        <button
          type="button"
          data-testid="workspace-file-open-browser"
          onClick={() => onOpenInBrowser(file)}
          aria-label={t('agentPanel.openInPreview')}
          title={t('agentPanel.openInPreview')}
          className={STRIP_BUTTON}
        >
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto" key={`${file.path}:${nonce}`}>
        {fileIsText(plan) ? (
          <FilePreviewBody
            preview={
              plan.kind === 'markdown' && plan.view === 'rendered'
                ? { kind: 'markdown', path: file.path, filename: file.name }
                : {
                    kind: 'code',
                    path: file.path,
                    filename: file.name,
                    language: plan.kind === 'code' ? plan.language : 'text',
                  }
            }
            onReload={reload}
          />
        ) : plan.kind === 'packed' ? (
          <FileParsed file={file} plan={plan} nonce={nonce} onOpenInBrowser={onOpenInBrowser} />
        ) : plan.kind === 'image' ||
          plan.kind === 'audio' ||
          plan.kind === 'video' ||
          plan.kind === 'frame' ? (
          <FileMedia file={file} plan={plan} nonce={nonce} onOpenInBrowser={onOpenInBrowser} />
        ) : (
          <FileHeld file={file} plan={plan} reason="binary" onOpenInBrowser={onOpenInBrowser} />
        )}
      </div>
    </div>
  )
}
