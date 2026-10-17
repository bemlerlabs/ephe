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
import { Check, Download, FileCode, FileText, FolderDown, Image as ImageIcon } from 'lucide-react'
import { ApiError, artifactFileUrl, fileUrl } from '@/lib/api'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { artifactPreviewMode, previewShowsInFrame } from '@/lib/previewMode'
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
  const mode = artifactPreviewMode(file.name, file.kind)
  // The pane shows a frame for whatever the browser can present. A PDF on the
  // desktop shell has no viewer in a frame (measured 2026-10-07, recorded in
  // previewMode), and 'none' is a format nothing renders at all — offering open
  // there would deliver a white box or a download the user did not ask for.
  const openable = mode !== 'none' && previewShowsInFrame(file.name, file.kind)
  const view = fileUrl(file.path)

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
            className="shrink-0 rounded px-1 py-0.5 text-ui-2xs font-medium text-brand transition-colors hover:bg-brand/10"
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
          className="rounded-md px-1.5 py-1 text-ui-2xs font-medium text-brand hover:bg-brand/10 transition-colors"
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
  )
}
