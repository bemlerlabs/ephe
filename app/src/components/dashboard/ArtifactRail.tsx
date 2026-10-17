/**
 * Ephe — P2-1 artifact pop-up of the running task.
 *
 * Since R4-A2 the workbench is a **page** (`/artifacts`): shelf, detail, search,
 * deadline and takeover all live there. This pop-up stays the quick view *out of
 * a task* — what was produced here, without a detour. It does not make a
 * decision the page also makes: the way into the library is a link, not a
 * second shelf.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Download, FileCode, FileText, FolderOpen, Image as ImageIcon, Library } from 'lucide-react'
import type { Activity, ChatMessage } from '@/types'
import { artifactFileUrl, fileUrl } from '@/lib/api'
import { previewSandbox, previewShowsInFrame, previewSrc } from '@/lib/previewMode'
import { useFocusReturn } from '@/hooks/useFocusReturn'

const IMG_TYPES = new Set(['svg', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'chart', 'image'])
const FRAME_TYPES = new Set(['pdf', 'html', 'deck', 'pptx'])

type ArtifactFilter = 'all' | 'docs' | 'visual' | 'office'
const FILTER_CATEGORIES: Record<Exclude<ArtifactFilter, 'all'>, Set<string>> = {
  docs: new Set(['pdf', 'html', 'deck', 'pptx', 'deck_studio']),
  visual: new Set(['svg', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'chart', 'image']),
  office: new Set(['xlsx', 'docx']),
}

function filterFor(fileType?: string, path?: string): ArtifactFilter {
  const t = (fileType || path?.split('.').pop() || '').toLowerCase()
  for (const [filter, set] of Object.entries(FILTER_CATEGORIES) as [
    Exclude<ArtifactFilter, 'all'>,
    Set<string>,
  ][]) {
    if (set.has(t)) return filter
  }
  return 'docs'
}

function previewKind(fileType?: string, path?: string): 'img' | 'frame' | 'none' {
  const t = (fileType || path?.split('.').pop() || '').toLowerCase()
  if (IMG_TYPES.has(t)) return 'img'
  if (FRAME_TYPES.has(t)) return 'frame'
  return 'none'
}

function IconFor({ kind }: { kind: 'img' | 'frame' | 'none' }) {
  if (kind === 'img') return <ImageIcon className="h-3.5 w-3.5 text-brand/70" />
  if (kind === 'frame') return <FileText className="h-3.5 w-3.5 text-brand/70" />
  return <FileCode className="h-3.5 w-3.5 text-brand/70" />
}

/**
 * A0: a card with an id asks for its bytes via the id (core/artifact_workbench
 * .artifact_target checks the allowed roots there). The path is the escape route
 * for sessions from before the id.
 */
function hrefFor(id: string | undefined, path: string | undefined, download = false): string {
  if (id) return artifactFileUrl(id, download)
  return path ? fileUrl(path) : ''
}

/**
 * R4 (A3): the way into the workbench runs via the request, never via a path.
 * If the artifact's turn id is known (tracked live or restored from the mirror),
 * the link scopes to exactly that request; otherwise the session remains the
 * narrowest truth we have.
 */
export function workbenchScope(sessionId?: string | null, turnId?: string): string {
  if (turnId) return `#/artifacts?turn=${encodeURIComponent(turnId)}`
  if (sessionId) return `#/artifacts?session=${encodeURIComponent(sessionId)}`
  return '#/artifacts'
}

export default function ArtifactRail({
  messages,
  sessionId,
  libraryOpen = false,
  onCloseLibrary,
}: {
  messages: ChatMessage[]
  /** R4 (A3): the session whose request gave birth to these cards — the link into
   *  the workbench asks after that, never after a path. */
  sessionId?: string | null
  libraryOpen?: boolean
  onCloseLibrary?: () => void
}) {
  const { t } = useTranslation()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filter, setFilter] = useState<ArtifactFilter>('all')
  // A card whose bytes are gone should say so instead of showing a broken image
  // (ephe_github_qr.png in the live index: 404, surface left speechless). The id
  // is remembered so that changing the selection takes the answer back.
  const [fehlendeKarte, setFehlendeKarte] = useState<string | null>(null)

  const sessionArtifacts = useMemo(
    () =>
      messages
        .flatMap((m) => m.activities ?? [])
        .filter((a): a is Activity & { path: string } => Boolean(a.path)),
    [messages],
  )
  // The turn id lives on the message, the activity underneath it — without this
  // mapping the way back would only be the session, not the request.
  const turnOf = useMemo(() => {
    const map = new Map<string, string>()
    for (const m of messages) {
      if (!m.turnId) continue
      for (const a of m.activities ?? []) map.set(a.id, m.turnId)
    }
    return map
  }, [messages])

  // R4-A2: the library is a page. The way there is the link above — this window
  // stays the quick view out of the running task and never opens itself by
  // triggering a navigation.

  // Controlled (the header toggle supplies onCloseLibrary): only the flag
  // opens/closes the pop-up. Uncontrolled (tests/legacy) the artifact rule applies.
  const controlled = onCloseLibrary !== undefined
  const geoeffnet = controlled ? Boolean(libraryOpen) : sessionArtifacts.length > 0

  // Wave 10 (persona 06, measured): the pop-up claims `aria-modal` and did not
  // honour it — the Tab walk left it after 10 stops and reached the toolbar
  // behind it, and nothing behind it was inert. useFocusReturn is the same
  // contract the settings overlay implements: focus in on open, Tab trapped,
  // background inert, handback to the toggle that opened it.
  const panelRef = useRef<HTMLDivElement>(null)
  const { onKeyDown: trapFocus, releaseFocus } = useFocusReturn({
    active: geoeffnet,
    containerRef: panelRef,
  })
  /** Closing paths hand focus back in the same task, before the portal unmounts. */
  const closeLibrary = () => {
    releaseFocus()
    onCloseLibrary?.()
  }

  // Esc closes the pop-up. The condition was inverted (`if (libraryOpen)
  // return`) and so hit exactly the path the product runs: controlled and open.
  // Measured in the review run — Escape did nothing, the `aria-modal` window
  // stayed above the chat and absorbed every further click, including the one
  // on the agent pane.
  useEffect(() => {
    if (!geoeffnet) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        releaseFocus()
        onCloseLibrary?.()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [geoeffnet, onCloseLibrary, releaseFocus])

  if (!geoeffnet) return null

  const counts: Record<ArtifactFilter, number> = {
    all: sessionArtifacts.length,
    docs: 0,
    visual: 0,
    office: 0,
  }
  for (const a of sessionArtifacts) counts[filterFor(a.fileType, a.path)]! += 1
  const visible =
    filter === 'all'
      ? sessionArtifacts
      : sessionArtifacts.filter((a) => filterFor(a.fileType, a.path) === filter)
  const selected =
    visible.find((a) => a.id === selectedId) ??
    visible[visible.length - 1] ??
    sessionArtifacts[sessionArtifacts.length - 1]!
  const previewPath = selected?.path
  const previewUrl = hrefFor(selected?.artifactId, selected?.path)
  const previewName = previewPath?.split('/').pop() ?? ''
  const kind = previewKind(selected?.fileType, previewPath)
  const bildFehlt = Boolean(selected?.id) && fehlendeKarte === selected?.id
  // In the desktop window there is no PDF viewer — there the card becomes the
  // answer instead of a blank frame.
  const rahmenMoeglich = previewShowsInFrame(previewName, selected?.fileType)
  const ohneRahmen =
    kind === 'none' || (kind === 'img' && bildFehlt) || (kind === 'frame' && !rahmenMoeglich)
  const filterChips: { id: ArtifactFilter; label: string }[] = [
    { id: 'all', label: t('artifacts.filterAll') },
    { id: 'docs', label: t('artifacts.filterDocs') },
    { id: 'visual', label: t('artifacts.filterVisual') },
    { id: 'office', label: t('artifacts.filterOffice') },
  ]

  return createPortal(
    <div
      ref={panelRef}
      // The aria-modal window is the trap boundary; tabIndex={-1} keeps a focus
      // target here even before the first card renders.
      tabIndex={-1}
      onKeyDown={trapFocus}
      role="dialog"
      aria-modal="true"
      aria-label={t('artifacts.title')}
      data-testid="artifact-modal"
      className="fixed inset-0 z-modal flex items-start justify-center pt-[6dvh] px-4 bg-canvas/60"
    >
      <div
        className="w-full max-w-[980px] max-h-[84dvh] float-surface bg-canvas flex flex-col overflow-hidden"
        data-float="3"
      >
        <div className="px-4 h-11 flex items-center gap-2 border-b border-hairline flex-shrink-0">
          <span className="text-ui-sm font-semibold text-foreground/80">
            {`${t('artifacts.title')} (${sessionArtifacts.length})`}
          </span>
          <span className="flex-1" />
          <a
            href={workbenchScope(sessionId)}
            onClick={closeLibrary}
            className="flex items-center gap-1.5 rounded-md border border-hairline px-2 py-1 text-ui-xs font-medium text-ink-soft hover:bg-surface hover:text-foreground/80 transition-colors"
            data-testid="artifact-open-page"
          >
            <FolderOpen className="h-3.5 w-3.5" />
            {t('artifacts.openWorkbench')}
          </a>
          {onCloseLibrary && (
            <button
              onClick={closeLibrary}
              aria-label={t('artifacts.closeLibrary')}
              data-testid="artifact-close"
              className="text-ink-faint hover:text-foreground p-1 rounded transition-colors hover:bg-surface"
            >
              ✕
            </button>
          )}
        </div>

        <div
          className="px-3 pt-2 flex flex-wrap gap-1 flex-shrink-0"
          role="group"
          aria-label={t('artifacts.filterGroup')}
        >
          {filterChips.map((chip) => (
            <button
              key={chip.id}
              onClick={() => setFilter(chip.id)}
              aria-pressed={filter === chip.id}
              data-testid={`artifact-filter-${chip.id}`}
              className={`px-2 py-0.5 rounded-md text-ui-xs font-medium transition-colors ${
                filter === chip.id
                  ? 'bg-brand/20 text-brand border border-brand/20'
                  : 'text-ink-soft border border-transparent hover:bg-surface hover:text-foreground/80'
              }`}
            >
              {chip.label} ({counts[chip.id]})
            </button>
          ))}
        </div>

        {/* Preview */}
        <div className="flex-1 min-h-0 flex flex-col px-3 py-2">
          <div className="flex-1 min-h-0 rounded-lg overflow-hidden border border-hairline bg-surface">
            {kind === 'img' && !bildFehlt && (
              <img
                src={previewUrl}
                alt={previewName}
                onError={() => setFehlendeKarte(selected?.id ?? null)}
                className="w-full h-full object-contain"
              />
            )}
            {kind === 'frame' && rahmenMoeglich && (
              <iframe
                src={previewSrc(previewUrl, previewName, selected?.fileType)}
                title={previewName}
                sandbox={previewSandbox(previewName, selected?.fileType)}
                style={{ colorScheme: 'light' }}
                className="w-full h-full bg-white"
              />
            )}
            {ohneRahmen && (
              <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-ink-soft text-ui-xs p-4 text-center">
                <FileCode className="h-8 w-8" />
                <span className="break-all">{previewName}</span>
                {(bildFehlt || (kind === 'frame' && !rahmenMoeglich)) && (
                  <span className="text-ink-faint" data-testid="artifact-preview-missing">
                    {bildFehlt ? t('artifacts.preview.missing') : t('artifacts.preview.noViewer')}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* The artifacts of this task */}
          <div className="flex-shrink-0 max-h-44 overflow-y-auto pt-2 space-y-1">
            {visible.map((a) => (
              <div key={a.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md">
                <button
                  onClick={() => setSelectedId(a.id)}
                  className={`flex min-w-0 flex-1 items-center gap-2 text-left text-ui-xs transition-colors ${
                    a.id === selected?.id ? 'text-brand' : 'text-ink-faint hover:text-foreground/80'
                  }`}
                >
                  <IconFor kind={previewKind(a.fileType, a.path)} />
                  <span className="truncate flex-1">{a.path.split('/').pop()}</span>
                </button>
                <a
                  href={workbenchScope(sessionId, turnOf.get(a.id))}
                  onClick={closeLibrary}
                  aria-label={`${t('artifacts.showInWorkbench')}: ${a.path.split('/').pop()}`}
                  title={t('artifacts.showInWorkbench')}
                  data-testid={`artifact-row-workbench-${a.id}`}
                  className="p-1 rounded hover:bg-surface text-ink-soft hover:text-foreground"
                >
                  <Library className="h-3.5 w-3.5" />
                </a>
                <a
                  href={hrefFor(a.artifactId, a.path, true)}
                  download
                  aria-label={`${t('artifacts.download')}: ${a.path.split('/').pop()}`}
                  className="p-1 rounded hover:bg-surface text-ink-soft hover:text-foreground"
                >
                  <Download className="h-3.5 w-3.5" />
                </a>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
