/**
 * Ephe — one card on the workbench shelf (R4/A1).
 *
 * Three gestures, cleanly separated: **view** (the row selects the preview),
 * **adopt** (a copy onto the user's disk — Ephe knows the target or the card
 * asks), **download** (the browser path, without Ephe remembering it). The
 * difference between adopt and download is the whole point: adopting leaves an
 * `adopted_path` behind and can therefore say whether the copy is still current.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import {
  Check,
  Download,
  ExternalLink,
  FileCode,
  FileText,
  FolderDown,
  FolderOpen,
  Image as ImageIcon,
  Star,
} from 'lucide-react'
import {
  ApiError,
  adoptArtifact,
  artifactFileUrl,
  favoriteArtifact,
  type ArtifactEntry,
} from '@/lib/api'
import { dateLocaleFor } from '@/lib/dateLocale'
import { canUseNativeFileActions, openInDefaultApp, revealInFinder } from '@/lib/fileActions'
import { adoptWithTarget } from './adoptFlow'

const IMG = new Set(['svg', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'chart', 'image'])
const FRAME = new Set(['pdf', 'html', 'deck', 'pptx'])

/** A stamp down to the minute — short enough for one row, unique enough to tell
 *  two cards of the same name apart. `precise` adds the second the index already
 *  stores, for the pair the minute cannot split; the date part stays as it is. */
function formatDateStamp(iso: string, language: string, precise = false): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(language, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: precise ? '2-digit' : undefined,
  }).format(date)
}

/**
 * The card's origin mark: the task that wrote it, falling back to the session
 * that birthed it. Exported because the shelf has to know which two rows carry
 * the same mark before it can ask a row to read finer.
 */
export function originOf(art: ArtifactEntry): string {
  return art.turn_id || art.session_id || ''
}

function CardIcon({ kind }: { kind: string }) {
  const t = kind.toLowerCase()
  if (IMG.has(t)) return <ImageIcon className="h-3.5 w-3.5 text-brand/70" />
  if (FRAME.has(t)) return <FileText className="h-3.5 w-3.5 text-brand/70" />
  return <FileCode className="h-3.5 w-3.5 text-brand/70" />
}

export default function ArtifactLibraryRow({
  art,
  selected,
  onSelect,
  onFavorite,
  ambiguous = false,
  preciseStamp = false,
}: {
  art: ArtifactEntry
  selected: boolean
  onSelect: () => void
  onFavorite: () => void
  /** Set by the shelf: the name repeats inside this group. Then the row carries
   *  its short provenance — the clock time only separates down to the minute. */
  ambiguous?: boolean
  /** Set by the shelf one step further: two cards of this group share the name AND
   *  the provenance mark, so neither of them separates the pair and the clock stops
   *  at the minute. The stamp then reads the birth the index actually stores — down
   *  to the second — and its title names that instant. */
  preciseStamp?: boolean
}) {
  const { t, i18n } = useTranslation()
  const [phase, setPhase] = useState<'idle' | 'asking' | 'busy' | 'done' | 'failed'>('idle')
  const [detail, setDetail] = useState('')
  // N4: the Finder verbs exist in the shell only. A refusal (a path outside the
  // folders Ephe may act on) gets one sentence beside the row; no toast.
  const nativeFiles = canUseNativeFileActions()
  const filePath = art.adopted_path || art.path
  const [fileNote, setFileNote] = useState('')
  const runFileAction = (action: (path: string) => Promise<boolean>) => {
    setFileNote('')
    void action(filePath).then((ok) => {
      if (!ok) setFileNote(t('artifacts.fileActionFailed'))
    })
  }
  // The assignment, not the directory: the same short tag that the provenance on
  // the right spells out — two rows, one way to recognise it.
  const herkunft = originOf(art)

  async function adopt(destination = '') {
    setPhase('busy')
    setDetail('')
    try {
      const result = destination
        ? await adoptArtifact(art.id, destination)
        : await adoptWithTarget(art.id, art.name, t('artifacts.adopt'))
      setDetail(result.adopted_path)
      setPhase('done')
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      // 422 = "no target remembered" is not an error message but a question.
      if (e instanceof ApiError && e.status === 422) {
        setPhase('asking')
        return
      }
      setDetail(message)
      setPhase('failed')
    }
  }

  return (
    <div
      className={`w-full rounded-md text-ui-xs transition-colors ${
        selected
          ? 'bg-brand/10 text-brand-deep'
          : 'text-ink-faint hover:bg-surface hover:text-foreground/80'
      }`}
      data-testid={`artifact-row-${art.id}`}
    >
      <div className="flex items-center gap-2 px-2 pt-1.5">
        {/* Before, all of this sat inside ONE role="button": screen-reader users
            got a single reading thread, and star, adopt and download were
            unreachable. A row is a place, not a button. */}
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={selected}
          className="flex min-h-9 max-lg:min-h-11 min-w-0 flex-1 items-center gap-2 rounded text-left focus-visible:outline-ring"
          data-testid={`artifact-select-${art.id}`}
        >
          <CardIcon kind={art.kind} />
          <span className="flex min-w-0 flex-1 items-baseline gap-1 truncate">
            <span className="truncate">{art.name}</span>
            {art.version > 1 && (
              <span className="ml-1 text-ui-2xs text-brand/60 font-mono">v{art.version}</span>
            )}
          </span>
        </button>
        {/* The house split for a row's verbs, from `agent/memoryRowCard.tsx`: a verb a glyph
            cannot carry shows its word, a well-known glyph keeps aria-label plus tooltip. Both
            take the touch floor, because a tooltip never renders on a phone. */}
        <button
          onClick={(e) => {
            e.stopPropagation()
            void favoriteArtifact(art.id, !art.favorite).then(onFavorite)
          }}
          aria-label={art.favorite ? t('artifacts.unfavorite') : t('artifacts.favorite')}
          title={art.favorite ? t('artifacts.unfavorite') : t('artifacts.favorite')}
          aria-pressed={art.favorite}
          className={`p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 shrink-0 rounded hover:bg-surface ${art.favorite ? 'text-status-warning' : 'text-ink-soft hover:text-foreground'}`}
        >
          <Star className={`h-3.5 w-3.5 ${art.favorite ? 'fill-status-warning' : ''}`} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            void adopt()
          }}
          disabled={phase === 'busy' || phase === 'done'}
          aria-label={`${t('artifacts.adopt')}: ${art.name}`}
          title={t('artifacts.adoptHint')}
          data-testid={`artifact-adopt-${art.id}`}
          className="flex shrink-0 items-center gap-1 rounded px-1.5 py-1 min-h-7 max-lg:min-h-11 text-ui-2xs font-medium text-ink-soft hover:text-foreground hover:bg-surface disabled:opacity-50"
        >
          {phase === 'done' ? (
            <Check className="h-3.5 w-3.5 text-status-success" />
          ) : (
            <FolderDown className="h-3.5 w-3.5" />
          )}
          <span>{t('artifacts.adopt')}</span>
        </button>
        <a
          href={artifactFileUrl(art.id, true)}
          download
          aria-label={`${t('artifacts.download')}: ${art.name}`}
          title={t('artifacts.downloadHint')}
          onClick={(e) => e.stopPropagation()}
          className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 shrink-0 rounded hover:bg-surface text-ink-soft hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" />
        </a>
        {nativeFiles && filePath && (
          <>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                runFileAction(revealInFinder)
              }}
              aria-label={`${t('artifacts.revealInFinder')}: ${art.name}`}
              title={t('artifacts.revealInFinder')}
              data-testid="artifact-reveal-in-finder"
              className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 shrink-0 rounded hover:bg-surface text-ink-soft hover:text-foreground"
            >
              <FolderOpen className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                runFileAction(openInDefaultApp)
              }}
              aria-label={`${t('artifacts.openDefault')}: ${art.name}`}
              title={t('artifacts.openDefault')}
              data-testid="artifact-open-default"
              className="p-1.5 min-h-7 min-w-7 max-lg:min-h-11 max-lg:min-w-11 shrink-0 rounded hover:bg-surface text-ink-soft hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          </>
        )}
      </div>

      {fileNote && (
        <p role="alert" className="px-2 pb-1 text-ui-2xs text-status-warning">
          {fileNote}
        </p>
      )}

      <div className="flex items-center gap-1.5 px-2 pb-1.5 text-ui-2xs text-ink-faint">
        {art.topic && art.topic !== art.name && <span className="truncate">{art.topic}</span>}
        {art.topic && art.topic !== art.name && <span aria-hidden>·</span>}
        <span className="flex-shrink-0 tabular-nums">
          {formatDistanceToNow(new Date(art.created_at), {
            addSuffix: true,
            locale: dateLocaleFor(i18n.language),
          })}
        </span>
        {/* Seven cards named `file-summary.pdf` on one shelf are no overview but a
            guessing game — exactly what the plan meant to solve with A3. The topic
            adds nothing here when it is the file name; then at least the
            minute-precise stamp tells them apart. */}
        {(!art.topic || art.topic === art.name) && (
          <span
            aria-hidden
            className="flex-shrink-0 tabular-nums text-ink-faint/70"
            title={art.created_at}
            data-testid={`artifact-stamp-${art.id}`}
          >
            {formatDateStamp(art.created_at, i18n.language, preciseStamp)}
          </span>
        )}
        {/* And where two cards were born in the same minute, what separates them
            last is the assignment that wrote them. Where even that mark repeats —
            one task, one name, one minute — the stamp above carries the stored
            second instead, and says in its title which instant it reads. */}
        {ambiguous && herkunft && (
          <span
            className="flex-shrink-0 font-mono text-ink-faint/60"
            title={herkunft}
            data-testid={`artifact-origin-${art.id}`}
          >
            #{herkunft.slice(0, 8)}
          </span>
        )}
      </div>

      {phase === 'asking' && (
        <form
          className="flex items-center gap-1.5 px-2 pb-1.5"
          onClick={(e) => e.stopPropagation()}
          onSubmit={(e) => {
            e.preventDefault()
            const value = new FormData(e.currentTarget).get('destination')
            void adopt(String(value ?? '').trim())
          }}
        >
          <input
            name="destination"
            autoFocus
            placeholder={t('artifacts.adoptDestination')}
            aria-label={t('artifacts.adoptDestination')}
            className="min-w-0 flex-1 rounded border border-hairline bg-surface px-2 py-1 text-ui-xs text-foreground/80 focus-ring"
          />
          <button
            type="submit"
            className="rounded bg-brand/20 px-2 py-1 text-ui-xs font-medium text-brand-deep"
            data-testid={`artifact-adopt-go-${art.id}`}
          >
            {t('artifacts.adoptGo')}
          </button>
          <button
            type="button"
            onClick={() => setPhase('idle')}
            className="rounded px-2 py-1 text-ui-xs text-ink-soft hover:text-foreground/80"
          >
            {t('artifacts.adoptCancel')}
          </button>
        </form>
      )}

      {(phase === 'done' || phase === 'failed') && detail && (
        <p
          className={`truncate px-2 pb-1.5 text-ui-2xs ${
            phase === 'failed' ? 'text-destructive' : 'text-ink-faint'
          }`}
          title={detail}
          data-testid={`artifact-adopt-state-${art.id}`}
        >
          {phase === 'failed' ? `${t('artifacts.adoptFailed')}: ${detail}` : detail}
        </p>
      )}
    </div>
  )
}
