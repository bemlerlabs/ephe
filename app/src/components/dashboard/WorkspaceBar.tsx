/**
 * Ephe — WorkspaceBar (W20, reference parity with the desktop pattern)
 *
 * Slim line above the composer: [📁 project ▾] + [🌿 branch ·dirty].
 * The chip opens a dropdown portalled to body (clip-immune, established pattern):
 * search, recently detected projects, „Ordner öffnen…" and „Außerhalb eines // language-gate: ignore (both are labels the German UI renders, locales/de.json:1452-1453)
 * Projekts arbeiten". The old composer chip + header label picker are gone — // language-gate: ignore (continuation of the quoted German label above)
 * ONE authoritative place for the workspace choice.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import {
  Check,
  ChevronDown,
  FolderClosed,
  FolderPlus,
  GitBranch,
  MessageCircle,
  Search,
} from 'lucide-react'
import { listProjects, type ProjectSummary } from '@/lib/api'
import FolderPickerDialog from './FolderPickerDialog'
import { useWorkspaceState, useWorkspaceSwitcher } from './WorkspacePicker'

interface WorkspaceBarProps {
  branch?: string
  dirty?: number
  git?: boolean
}

export default function WorkspaceBar({ branch, dirty = 0, git = false }: WorkspaceBarProps) {
  const { t } = useTranslation()
  const ws = useWorkspaceState()
  const { pickerOpen, openPicker, closePicker, pick } = useWorkspaceSwitcher()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const chipRef = useRef<HTMLButtonElement | null>(null)
  const [pos, setPos] = useState<{ left: number; bottom: number } | null>(null)

  const syncPos = useCallback(() => {
    const el = chipRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setPos({ left: r.left, bottom: window.innerHeight - r.top + 6 })
  }, [])

  useEffect(() => {
    if (!open) return
    syncPos()
    let cancelled = false
    listProjects()
      .then((r) => {
        if (!cancelled) setProjects(r.projects ?? [])
      })
      .catch(() => {
        if (!cancelled) setProjects([])
      })
    return () => {
      cancelled = true
    }
  }, [open, syncPos])

  const filtered = projects.filter(
    (p) =>
      !query.trim() ||
      p.name.toLowerCase().includes(query.trim().toLowerCase()) ||
      p.path.toLowerCase().includes(query.trim().toLowerCase()),
  )

  function handlePick(path: string) {
    setOpen(false)
    void pick(path)
  }

  function handleWorkOutside() {
    setOpen(false)
    // Empty input = the documented reset to the server default
    // (F semantics in POST /api/settings) — the entry reads „außerhalb eines Projekts". // language-gate: ignore (German wording of the workOutside entry, locales/de.json:1453)
    void pick('')
  }

  // U1b: Escape dismisses the workspace menu (keyboard parity with the
  // sidebar context menu, which already handles Escape).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div
      className="flex items-center gap-2 w-full max-w-3xl mx-auto px-4 pb-1.5 max-sm:hidden"
      data-testid="workspace-bar"
    >
      <button
        ref={chipRef}
        type="button"
        onClick={() => {
          setOpen((v) => !v)
          syncPos()
        }}
        aria-expanded={open}
        aria-haspopup="menu"
        data-testid="workspace-bar-chip"
        title={t('workspacePicker.title')}
        className="inline-flex items-center gap-1.5 min-w-0 min-h-6 max-w-72 rounded-md border border-hairline bg-surface px-2 py-0.5 text-ui-sm text-ink-faint hover:text-foreground hover:border-brand/30 transition-colors"
      >
        <FolderClosed className="h-3.5 w-3.5 shrink-0 text-brand/60" aria-hidden="true" />
        <span className="truncate">
          {ws.set && ws.name ? ws.name : t('workspaceBar.neutralWorkspace')}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 opacity-50 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {git && branch && (
        <span
          data-testid="workspace-bar-branch"
          title={t('header.branchChip')}
          className="inline-flex items-center gap-1 min-h-6 rounded-md border border-hairline bg-surface px-2 py-0.5 text-ui-sm text-ink-soft"
        >
          <GitBranch className="h-3.5 w-3.5 shrink-0 text-brand/50" aria-hidden="true" />
          <span className="truncate max-w-32">{branch}</span>
          {dirty > 0 && <span className="text-status-warning/70">·{dirty}</span>}
        </span>
      )}

      {open &&
        pos &&
        createPortal(
          <div
            role="menu"
            data-testid="workspace-bar-menu"
            style={{ left: pos.left, bottom: pos.bottom }}
            className="fixed z-modal w-[min(420px,92vw)] float-surface py-1.5"
          >
            <div className="px-2 pb-1.5">
              <div className="flex items-center gap-2 rounded-lg border border-hairline bg-canvas px-2.5 py-1.5">
                <Search className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t('workspaceBar.searchPlaceholder')}
                  aria-label={t('workspaceBar.searchPlaceholder')}
                  className="w-full bg-transparent text-ui-xs text-foreground outline-none placeholder:text-ink-faint"
                />
              </div>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {filtered.length === 0 && (
                <p className="px-3 py-2 text-ui-xs text-ink-faint">
                  {t('workspaceBar.noProjects')}
                </p>
              )}
              {filtered.map((p) => {
                const active = !!ws.name && ws.set && p.name === ws.name
                return (
                  <button
                    key={p.path}
                    type="button"
                    role="menuitem"
                    onClick={() => handlePick(p.path)}
                    title={p.path}
                    className="w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:bg-surface hover:text-foreground transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                  >
                    <FolderClosed
                      className="h-3.5 w-3.5 shrink-0 text-brand/50"
                      aria-hidden="true"
                    />
                    <span className="truncate">{p.name}</span>
                    {active && (
                      <Check
                        className="ml-auto h-3.5 w-3.5 shrink-0 text-brand"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                )
              })}
            </div>
            <div className="mt-1 border-t border-hairline pt-1">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  openPicker()
                }}
                className="w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:bg-surface hover:text-foreground transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                <FolderPlus className="h-3.5 w-3.5 shrink-0 text-brand/50" aria-hidden="true" />
                {t('workspaceBar.openFolder')}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={handleWorkOutside}
                className="w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:bg-surface hover:text-foreground transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                <MessageCircle className="h-3.5 w-3.5 shrink-0 text-brand/50" aria-hidden="true" />
                {t('workspaceBar.workOutside')}
              </button>
            </div>
          </div>,
          document.body,
        )}

      <FolderPickerDialog
        open={pickerOpen}
        onClose={closePicker}
        onPick={(p) => {
          void pick(p)
        }}
      />
    </div>
  )
}
