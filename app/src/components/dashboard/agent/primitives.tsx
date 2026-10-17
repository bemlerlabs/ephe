'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FolderOpen, MessagesSquare } from 'lucide-react'
import { getSettings } from '@/lib/api'

export function useWorkspaceDir(): string | null {
  const [dir, setDir] = useState<string | null>(null)
  useEffect(() => {
    getSettings()
      .then((s) => setDir(s.workspace_dir || null))
      .catch(() => setDir(null))
  }, [])
  return dir
}

export function WorkspaceBadge({ dir }: { dir: string | null }) {
  const { t } = useTranslation()
  if (!dir) return null
  return (
    <div className="flex items-center gap-1.5 px-3 py-1 border-b border-hairline bg-surface text-ui-xs text-ink-faint font-mono flex-shrink-0 overflow-hidden">
      <FolderOpen className="h-3 w-3 text-brand/60 flex-shrink-0" aria-hidden="true" />
      <span className="text-brand/60 flex-shrink-0">{t('agentPanel.workspace')}</span>
      <span className="truncate" title={dir}>
        {dir}
      </span>
    </div>
  )
}

// The event names live in lib/panelEvents (single source); re-exported so the
// existing consumers of this module keep working.
export type Tab =
  | 'preview'
  | 'terminal'
  | 'git'
  | 'files'
  | 'audit'
  | 'trajectory'
  | 'subagents'
  | 'memory'
  | 'browser'
  | 'side'

// P6 B1 (ref-10): the + menu is normalised to exactly four entries — the
// menu key order is part of the contract. P6 B5: 'browser' is the
// menu name of the ONE URL pane (tab key 'preview'); 'review' maps to
// the git pane, 'side' to the side conversation.
export const PANEL_MENU_KEYS: { menuKey: string; tab: Tab }[] = [
  { menuKey: 'side', tab: 'side' },
  { menuKey: 'review', tab: 'git' },
  { menuKey: 'terminal', tab: 'terminal' },
  { menuKey: 'browser', tab: 'preview' },
]

// Round G (2026-09-07, reference parity): the pane carries real multi-tabs.
// Opened pages appear as pills (with a close button), the + menu offers the 4
// menu keys and "recently closed tabs" to restore. When all are closed the pane
// shows an empty state with open-cards.
// P6 B5: 'browser' is no longer its own tab type — deduped into 'preview'.
export const TAB_KEYS: Tab[] = [
  'preview',
  'terminal',
  'git',
  'files',
  'audit',
  'trajectory',
  'subagents',
  'memory',
  'side',
]

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export type TabState = { open: Tab[]; active: Tab | null; recent: { tab: Tab; closedAt: number }[] }

export function relTime(ts: number): string {
  const m = Math.max(0, Math.round((Date.now() - ts) / 60000))
  if (m < 60) return `${m}m`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h`
  return `${Math.round(h / 24)}d`
}

/** P0-1: the ANSI-16 colour palette (JetBrains/Vercel standard tones) for the
 *  terminal tab. Index = SGR code 30..37 / 90..97. */
export const ANSI_FG: Record<number, string> = {
  30: '#4b5259',
  31: '#f47474',
  32: '#6cc78a',
  33: '#e0c470',
  34: '#6aa7f0',
  35: '#c586e0',
  36: '#5fc7c7',
  37: '#d6dbe0',
  90: '#6e7680',
  91: '#ff8080',
  92: '#7ad89a',
  93: '#f0d480',
  94: '#80b8ff',
  95: '#d89af0',
  96: '#70dada',
  97: '#f0f4f8',
}

/** P0-1: a minimal ANSI→React renderer (SGR 1/2/3/30-37/90-97/39).
 *  Not a full parser — only what the shell output actually delivers. What cannot
 *  be parsed stays as text; the escape sequences themselves are swallowed. */
export function renderAnsi(src: string): React.ReactNode {
  if (!src) return src
  const out: React.ReactNode[] = []
  let bold = false
  let dim = false
  let italic = false
  let color: string | undefined
  let key = 0
  // eslint-disable-next-line no-control-regex -- ANSI escape parsing needs the ESC control char (\x1b) as a literal
  const esc = /\x1b\[([0-9;]*)m/g
  let last = 0
  const push = (text: string) => {
    if (!text) return
    out.push(
      <span
        key={key++}
        style={{
          color,
          fontWeight: bold ? 700 : undefined,
          opacity: dim ? 0.7 : undefined,
          fontStyle: italic ? 'italic' : undefined,
        }}
      >
        {text}
      </span>,
    )
  }
  let m: ReturnType<typeof esc.exec> | null
  while ((m = esc.exec(src)) !== null) {
    push(src.slice(last, m.index))
    last = esc.lastIndex
    const raw = m[1] ?? ''
    const codes = raw === '' ? ['0'] : raw.split(';')
    for (const c of codes) {
      const n = Number(c)
      if (n === 0) {
        bold = false
        dim = false
        italic = false
        color = undefined
      } else if (n === 1) bold = true
      else if (n === 2) dim = true
      else if (n === 3) italic = true
      else if (n === 39) color = undefined
      else if (ANSI_FG[n] !== undefined) color = ANSI_FG[n]
    }
  }
  push(src.slice(last))
  return out
}

/**
 * Visibility wave: the entrance to a helper's own chat. Defined at module level so
 * that a row re-render (the live ticker in the helpers tab) cannot swap the click
 * out from under the finger.
 */
export function OpenHelperChatButton({
  agentId,
  chatSessionId,
  onOpen,
}: {
  agentId: string
  chatSessionId?: string
  onOpen: (agentId: string, chatSessionId?: string) => void
}) {
  const { t } = useTranslation()
  const label = t('agentPanel.openHelperChat')
  return (
    <button
      type="button"
      data-testid={`subagent-open-chat-${agentId}`}
      title={label}
      onClick={(e) => {
        e.stopPropagation()
        onOpen(agentId, chatSessionId)
      }}
      className="shrink-0 inline-flex items-center gap-1 rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ui-xs text-ink-soft hover:text-foreground hover:border-brand/30 transition-colors min-h-9 max-lg:min-h-11"
    >
      <MessagesSquare className="h-3 w-3 opacity-70" aria-hidden="true" />
      <span className="hidden xl:inline">{label}</span>
    </button>
  )
}
