import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Check, ChevronRight, FolderOpen, FolderPlus, Loader2, Monitor, X } from 'lucide-react'
import { createWorkspaceFolder, listFs, type FsListing } from '@/lib/api'

/**
 * F round 4: workspace folder dialog (AI-client parity) — instead of typing an
 * absolute path, the user browses to the project (read-only via /api/fs).
 * W19 F3: desktop quick pick + "New folder" right in the dialog (POST /api/fs/mkdir).
 */
export default function FolderPickerDialog({
  open,
  onClose,
  onPick,
}: {
  open: boolean
  onClose: () => void
  onPick: (path: string) => void
}) {
  const { t } = useTranslation()
  const [listing, setListing] = useState<FsListing | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // W19 F3: inline "New folder" — type a name, create it in the current folder.
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  const load = useCallback((path?: string) => {
    setLoading(true)
    setError(null)
    listFs(path)
      .then(setListing)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  async function handleCreateFolder() {
    if (!listing || !newName.trim() || creating) return
    setCreating(true)
    setError(null)
    try {
      const res = await createWorkspaceFolder(listing.path, newName.trim())
      setNewName('')
      await load(res.path) // move into the new folder — "Choose" starts from there
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCreating(false)
    }
  }

  // Deploy-check P2-3: Escape must close the dialog (the shortcuts overlay
  // promises "Close panel / dialog: Esc"). Listener on window because the
  // dialog content is not guaranteed to hold focus.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, onClose])

  if (!open) return null

  const dirs = (listing?.entries ?? []).filter((e) => e.type === 'dir')
  const crumbs = listing ? listing.path.split('/').filter(Boolean) : []

  // Render through a body portal: ancestors with `backdrop-filter` (the
  // glass-control composer) become the containing block for position:fixed and
  // TRAP the dialog inside them (clipped, no page backdrop). Deploy polish P1.
  return createPortal(
    <div
      className="fixed inset-0 z-modal flex items-center justify-center bg-canvas/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={t('workspacePicker.title')}
    >
      <div className="w-[min(520px,92vw)] max-h-[70vh] flex flex-col float-surface" data-float="3">
        <div className="flex items-center justify-between px-4 h-12 border-b border-hairline flex-shrink-0">
          <h3 className="text-ui-sm font-semibold text-foreground/90">
            {t('workspacePicker.title')}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('chat.cancel')}
            className="p-1 rounded-md text-ink-soft hover:text-foreground hover:bg-surface transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Breadcrumb + W19 F3 quick pick / new folder */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-hairline text-ui-xs text-ink-soft font-mono overflow-x-auto flex-shrink-0">
          {listing && (
            <>
              <button
                type="button"
                className="hover:text-brand transition-colors"
                onClick={() => load(listing.home)}
              >
                ~
              </button>
              {crumbs.slice(1).map((c, i) => (
                <span key={i} className="flex items-center gap-1">
                  <ChevronRight className="h-3 w-3 opacity-40" />
                  <span className={i === crumbs.length - 2 ? 'text-foreground/80' : ''}>{c}</span>
                </span>
              ))}
            </>
          )}
          {/* Desktop quick pick: an allowed standard root, the most common project location */}
          <button
            type="button"
            data-testid="folder-quick-desktop"
            onClick={() => load('~/Desktop')}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-hairline bg-surface-raised px-2 py-0.5 text-ui-sm text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors font-sans flex-shrink-0"
          >
            <Monitor className="h-3 w-3" aria-hidden="true" />
            {t('workspacePicker.quickDesktop')}
          </button>
        </div>

        {/* W19 F3: new folder inside the currently displayed directory */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-hairline flex-shrink-0">
          <input
            data-testid="folder-new-input"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleCreateFolder()
            }}
            placeholder={t('workspacePicker.newFolderPlaceholder')}
            aria-label={t('workspacePicker.newFolderAria')}
            className="min-w-0 flex-1 rounded-lg border border-hairline bg-canvas px-3 py-1.5 text-ui-xs text-foreground focus-ring placeholder:text-ink-faint"
          />
          <button
            type="button"
            data-testid="folder-new-create"
            onClick={() => void handleCreateFolder()}
            disabled={!listing || !newName.trim() || creating}
            aria-label={t('workspacePicker.newFolderAria')}
            className="inline-flex items-center gap-1 rounded-lg border border-hairline bg-surface-raised px-2.5 py-1.5 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive disabled:opacity-40 transition-colors flex-shrink-0"
          >
            {creating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
            ) : (
              <FolderPlus className="h-3.5 w-3.5 text-brand/70" aria-hidden="true" />
            )}
            {t('workspacePicker.newFolder')}
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-2">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-brand/60" />
            </div>
          ) : error ? (
            <p className="text-ui-xs text-status-danger/80 p-3">{error}</p>
          ) : dirs.length === 0 ? (
            <p className="text-ui-xs text-ink-faint p-3">{t('workspacePicker.empty')}</p>
          ) : (
            dirs.map((d) => (
              <button
                key={d.name}
                type="button"
                onClick={() =>
                  load(listing ? `${listing.path.replace(/\/$/, '')}/${d.name}` : undefined)
                }
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-ui-sm text-foreground/80 hover:bg-surface-interactive hover:text-foreground transition-colors text-left"
              >
                <FolderOpen className="h-4 w-4 text-brand/70 flex-shrink-0" aria-hidden="true" />
                <span className="truncate">{d.name}</span>
              </button>
            ))
          )}
        </div>

        <div className="flex items-center justify-between gap-2 px-4 h-14 border-t border-hairline flex-shrink-0">
          <span
            className="text-ui-sm text-ink-faint font-mono truncate flex-1"
            title={listing?.path}
          >
            {listing?.path}
          </span>
          <button
            type="button"
            disabled={!listing}
            onClick={() => {
              if (listing) {
                onPick(listing.path)
                onClose()
              }
            }}
            className="flex items-center gap-1.5 rounded-lg bg-brand/20 text-brand hover:bg-brand/20 px-3 py-1.5 text-ui-xs font-medium disabled:opacity-40 transition-colors"
          >
            <Check className="h-3.5 w-3.5" />
            {t('workspacePicker.choose')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
