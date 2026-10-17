/**
 * Ephe — the detail view of a workbench card (R4/A2).
 *
 * On the right stands what the row knows: the preview, the gestures, and the
 * provenance (session, call, version line, adoption state, expiry). Nothing here
 * claims anything about the file that the index does not carry — an empty adopt
 * path shows as "not adopted", never as an error.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Check, Download, FolderDown, History, RefreshCw, Star, Trash2 } from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import type { ArtifactEntry } from '@/lib/api'
import {
  artifactFileUrl,
  favoriteArtifact,
  getArtifact,
  listArtifactVersions,
  removeArtifact,
  type ArtifactDetail,
} from '@/lib/api'
import ArtifactPreviewPane from './preview'
import { formatBytes, formatDateTime } from '@/lib/dateLocale'
import ArtifactTags from './tags'
import ArtifactProvenanceBlock from './provenance'
import { adoptWithTarget } from './adoptFlow'
import { ApiError, type ArtifactAdoptResult } from '@/lib/api'
import { kindLabel } from './shelf'

const BUTTON =
  'inline-flex min-h-8 items-center gap-1.5 rounded-md px-2.5 text-ui-xs font-medium transition-colors'

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-ui-xs">
      <dt className="w-28 flex-shrink-0 text-ink-faint">{label}</dt>
      <dd className="min-w-0 flex-1 break-all text-foreground/80">{value}</dd>
    </div>
  )
}

export default function ArtifactDetailPane({
  id,
  onChanged,
}: {
  id: string
  onChanged: () => void
}) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [art, setArt] = useState<ArtifactDetail | null>(null)
  const [versions, setVersions] = useState<ArtifactEntry[] | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [adoptBusy, setAdoptBusy] = useState(false)
  const [adoptNote, setAdoptNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setArt(null)
    setVersions(null)
    setConfirmDelete(false)
    setError(null)
    getArtifact(id)
      .then((r) => {
        if (cancelled) return
        setArt(r)
        if (r.root_id)
          listArtifactVersions(r.root_id).then((v) => !cancelled && setVersions(v.versions))
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      cancelled = true
    }
  }, [id, nonce])

  if (error) {
    return (
      <div className="flex flex-col items-start gap-2 p-4" data-testid="artifact-detail-error">
        <p role="alert" className="text-ui-xs text-destructive">
          {t('artifacts.page.detailFailed')}: {error}
        </p>
        <button
          type="button"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="artifact-detail-retry"
          className="inline-flex min-h-7 items-center gap-1.5 rounded-lg border border-hairline px-3 py-1.5 text-ui-xs font-medium text-foreground transition-colors hover:bg-surface focus-ring"
        >
          <RefreshCw className="h-3 w-3" />
          {t('agentPanel.retry')}
        </button>
      </div>
    )
  }
  if (!art) {
    return <LoadingRow label={t('artifacts.page.loading')} className="h-full justify-center" />
  }

  /* The card on the right shows the copy state — so adopting has to be possible
     from here too, not only from the row on the left. */
  async function adopt() {
    if (!art) return
    setAdoptBusy(true)
    setAdoptNote(null)
    try {
      const r: ArtifactAdoptResult = await adoptWithTarget(art.id, art.name, t('artifacts.adopt'))
      setAdoptNote(r.adopted_path)
      setArt({
        ...art,
        adopted_path: r.adopted_path,
        adopted_hash: r.adopted_hash,
        adopted_state: 'current',
      })
      onChanged()
    } catch (e) {
      setAdoptNote(
        e instanceof ApiError && e.status === 422
          ? t('artifacts.adoptDestination')
          : String((e as Error).message ?? e),
      )
    } finally {
      setAdoptBusy(false)
    }
  }

  async function toggleFavorite() {
    if (!art) return
    await favoriteArtifact(art.id, !art.favorite)
    onChanged()
    setArt({ ...art, favorite: !art.favorite })
  }

  async function remove(withFile: boolean) {
    if (!art) return
    setBusy(true)
    try {
      await removeArtifact(art.id, withFile)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  const adoptedState = art.adopted_state
  const adopted = art.adopted_path
    ? `${art.adopted_path} · ${t(`artifacts.page.adopted.${adoptedState}`)}${adoptNote ? ` — ${adoptNote}` : ''}`
    : adoptNote || t('artifacts.page.adopted.none')
  const line = (versions ?? []).filter((v) => v.version > 1)

  return (
    <div className="flex h-full min-h-0 flex-col gap-3" data-testid="artifact-detail">
      <div className="flex min-w-0 items-baseline gap-2">
        <h3
          className="min-w-0 truncate font-display text-ui-sm font-semibold text-foreground/90"
          title={art.name}
        >
          {art.name}
        </h3>
        <span className="flex-shrink-0 text-ui-2xs text-ink-faint">
          {kindLabel(art.kind, t)} · {formatBytes(art.size, i18n.language)}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-hairline bg-surface">
        <ArtifactPreviewPane art={art} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {/* The page promises "you decide what lands on your disk" — then adopting
            is the action and downloading is only a route. Downloading held the
            emphasis. When the copy is already current, adopt is disabled; then the
            emphasis belongs to the other button, not to a grey one. */}
        <a
          href={artifactFileUrl(art.id, true)}
          download
          className={`${BUTTON} ${
            adoptedState === 'current'
              ? 'bg-brand/20 text-brand'
              : 'border border-hairline text-ink-soft hover:bg-surface hover:text-foreground/80'
          }`}
          data-testid="artifact-detail-download"
        >
          <Download className="h-3.5 w-3.5" />
          {t('artifacts.download')}
        </a>
        <button
          onClick={() => void adopt()}
          disabled={adoptBusy || adoptedState === 'current'}
          className={`${BUTTON} ${
            adoptedState === 'current'
              ? 'border border-hairline text-ink-soft hover:bg-surface hover:text-foreground/80'
              : 'bg-brand/20 text-brand'
          }`}
          data-testid="artifact-detail-adopt"
        >
          <FolderDown className="h-3.5 w-3.5" />
          {t('artifacts.adopt')}
        </button>
        <button
          onClick={toggleFavorite}
          aria-pressed={art.favorite}
          className={`${BUTTON} ${art.favorite ? 'text-status-warning' : 'text-ink-soft hover:text-foreground/80'}`}
        >
          <Star className={`h-3.5 w-3.5 ${art.favorite ? 'fill-status-warning' : ''}`} />
          {t('artifacts.favorite')}
        </button>
        <span className="flex-1" />
        {confirmDelete ? (
          <>
            <span className="text-ui-xs text-foreground/80">{t('artifacts.page.deleteAsk')}</span>
            <button
              onClick={() => void remove(true)}
              disabled={busy}
              className={`${BUTTON} border border-destructive/40 text-destructive`}
              data-testid="artifact-detail-delete-file"
            >
              {t('artifacts.page.deleteFile')}
            </button>
            <button
              onClick={() => void remove(false)}
              disabled={busy}
              className={`${BUTTON} text-ink-soft hover:text-foreground/80`}
            >
              {t('artifacts.page.deleteIndexOnly')}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className={`${BUTTON} text-ink-soft hover:text-foreground/80`}
            >
              {t('artifacts.expiry.cancel')}
            </button>
          </>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className={`${BUTTON} text-destructive hover:bg-surface`}
            data-testid="artifact-detail-delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t('artifacts.page.remove')}
          </button>
        )}
      </div>

      <dl className="space-y-1 rounded-lg border border-hairline bg-surface p-2.5">
        <Meta label={t('artifacts.page.kind')} value={kindLabel(art.kind, t)} />
        <Meta
          label={t('artifacts.page.created')}
          value={formatDateTime(art.created_at, i18n.language)}
        />
        <Meta
          label={t('artifacts.page.viewed')}
          value={formatDateTime(art.viewed_at, i18n.language)}
        />
        <Meta label={t('artifacts.page.session')} value={art.session_id || '—'} />
        {art.turn_id && art.call_id && (
          <Meta label={t('artifacts.page.call')} value={art.call_id} />
        )}
        <Meta label={t('artifacts.page.location')} value={art.path} />
        <Meta
          label={t('artifacts.page.origin')}
          value={
            art.origin_path && art.origin_path !== art.path
              ? art.origin_path
              : t('artifacts.page.originSame')
          }
        />
        <Meta label={t('artifacts.page.adoptedLabel')} value={adopted} />
        <Meta
          label={t('artifacts.page.expiry')}
          value={
            art.keep
              ? t('artifacts.page.kept')
              : art.expires_at
                ? `${formatDateTime(art.expires_at, i18n.language)} · ${t('artifacts.page.expiryHint', { days: 30 })}`
                : t('artifacts.page.expiryNone')
          }
        />
      </dl>

      <ArtifactTags art={art} onSaved={onChanged} />

      <ArtifactProvenanceBlock
        id={art.id}
        // R4 (A3): the way back. /chat receives the parameters itself and opens the
        // replay tab — this card claims no state, it only describes where the file
        // came from.
        onOpenTask={
          art.session_id
            ? () => navigate(`/chat?session=${encodeURIComponent(art.session_id)}&replay=1`)
            : undefined
        }
      />

      {line.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface p-2.5">
          <p className="mb-1.5 flex items-center gap-1.5 text-ui-2xs font-semibold uppercase tracking-wide text-ink-faint">
            <History className="h-3 w-3" />
            {t('artifacts.page.versions')}
          </p>
          <ul className="space-y-1">
            {(versions ?? []).map((v) => (
              <li key={v.id} className="flex items-center gap-2 text-ui-xs">
                <span className="font-mono text-brand/80">v{v.version}</span>
                <span className="min-w-0 flex-1 truncate text-foreground/80">{v.name}</span>
                <span className="text-ink-faint">
                  {formatDateTime(v.created_at, i18n.language)}
                </span>
                {v.id === art.id && <Check className="h-3.5 w-3.5 text-brand" aria-hidden />}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="flex items-center gap-1.5 text-ui-2xs text-ink-faint">
        <FolderDown className="h-3 w-3" aria-hidden />
        {t('artifacts.page.workbenchNote')}
      </p>
    </div>
  )
}
