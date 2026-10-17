/**
 * Ephe — Toolbar Row (R26, mockup second header line)
 *
 * R39 (P2, 1:1 reference): line 2 carries the four tab buttons
 * (Files / Preview / Develop→Terminal / Git Console) + ⌘K palette. The
 * fifth button was Steps, a second list of the same work in another
 * vocabulary; the plan's own timeline (the plan card in the message) is
 * the one step surface, so the button is gone with that panel tab.
 * The three meta values (uptime / free disk / auto read-aloud) live as a
 * ToolbarMeta group in the right icon island of the header (ChatLayout) —
 * the test IDs stay unchanged: toolbar-meta, toolbar-autospeak.
 *
 * P1 [F4] menu character as in the reference: the ▾ is now a real
 * dropdown — clicking the chip jumps into the tab as before, the ▾ opens
 * a menu with intelligent actions (the latest artifacts of the session,
 * neighbouring panel tabs). The active panel tab marks its chip
 * (PANEL_STATE_EVENT broadcast from the AgentPanel).
 */
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  FolderClosed,
  MonitorPlay,
  TerminalSquare,
  GitBranch,
  Volume2,
  FileBox,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PREVIEW_OPEN_EVENT, PANEL_STATE_EVENT } from '@/lib/panelEvents'
import { AUTOSPEAK_CHANGED_EVENT, isAutospeakActive, setAutospeak } from '@/lib/autospeak'
import { formatFree, useSystemMetrics } from './MetricsGauges'
import { fileUrl } from '@/lib/api'
import type { ChatMessage } from '@/types'

const TOOLS = [
  { tab: 'files', labelKey: 'toolbar.files', Icon: FolderClosed },
  { tab: 'preview', labelKey: 'toolbar.preview', Icon: MonitorPlay },
  { tab: 'terminal', labelKey: 'toolbar.develop', Icon: TerminalSquare },
  { tab: 'git', labelKey: 'toolbar.gitConsole', Icon: GitBranch },
] as const

interface MenuItem {
  label: string
  detail?: { tab: string } | { url: string }
  Icon?: React.ComponentType<{ className?: string }>
}

/**
 * Meta values of the old toolbar-meta (moved into the header island by R39):
 * backend uptime, free disk space, per-session auto read-aloud toggle.
 */
export function ToolbarMeta({ sessionId }: { sessionId?: string }) {
  const { t } = useTranslation()
  const metrics = useSystemMetrics()
  const [autoSpeak, setAutoSpeakState] = useState(() => isAutospeakActive(sessionId))
  useEffect(() => {
    setAutoSpeakState(isAutospeakActive(sessionId))
    const sync = () => setAutoSpeakState(isAutospeakActive(sessionId))
    window.addEventListener(AUTOSPEAK_CHANGED_EVENT, sync)
    return () => window.removeEventListener(AUTOSPEAK_CHANGED_EVENT, sync)
  }, [sessionId])

  const uptimeMin =
    metrics?.uptime_s != null && Number.isFinite(metrics.uptime_s)
      ? Math.max(1, Math.round(metrics.uptime_s / 60))
      : null

  return (
    <div
      className="hidden md:flex items-center gap-2 text-ui-xs text-ink-faint min-w-0"
      data-testid="toolbar-meta"
    >
      {uptimeMin !== null && (
        <span
          className="tabular-nums truncate min-w-0"
          title={t('toolbar.uptime')}
          aria-label={t('toolbar.uptime')}
        >
          {t('toolbar.uptimeShort', { minutes: uptimeMin })}
        </span>
      )}
      {metrics && metrics.disk_free_bytes > 0 && (
        <span
          className="tabular-nums truncate min-w-0"
          title={t('metrics.free')}
          aria-label={t('metrics.free')}
        >
          {formatFree(metrics.disk_free_bytes, t)}
        </span>
      )}
      <button
        onClick={() => setAutospeak(sessionId, !autoSpeak)}
        aria-pressed={autoSpeak}
        aria-label={t('toolbar.autoSpeak')}
        data-testid="toolbar-autospeak"
        className={`inline-flex items-center gap-1.5 min-w-0 min-h-6 rounded-md px-1.5 py-0.5 transition-colors ${
          autoSpeak
            ? 'text-brand bg-brand/20'
            : 'text-ink-faint hover:text-foreground/70 hover:bg-surface-interactive'
        }`}
      >
        <Volume2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate min-w-0">{t('toolbar.autoSpeak')}</span>
      </button>
    </div>
  )
}

export default function ToolbarRow({
  messages = [],
}: {
  /** Messages of the active session — source for the "latest artifacts" menu entries. */
  messages?: ChatMessage[]
}) {
  const { t } = useTranslation()
  // [F4] active panel tab (broadcast by the AgentPanel through PANEL_STATE_EVENT)
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [menu, setMenu] = useState<{ tab: string; rect: DOMRect } | null>(null)

  useEffect(() => {
    const onState = (e: Event) => {
      const d = (e as CustomEvent<{ open?: boolean; tab?: string }>).detail
      setActiveTab(d?.open ? (d.tab ?? null) : null)
    }
    window.addEventListener(PANEL_STATE_EVENT, onState)
    return () => window.removeEventListener(PANEL_STATE_EVENT, onState)
  }, [])

  // Escape closes the open chip menu (keyboard parity with the popovers).
  useEffect(() => {
    if (!menu) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menu])

  const openTab = (tab: string) => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
    setMenu(null)
  }
  const openArtifact = (url: string) => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url } }))
    setMenu(null)
  }

  // [F4] "latest previews": the most recent artifacts of the active session
  // (newest first, deduplicated, max. 3) as direct open actions.
  const recentArtifacts = useMemo(() => {
    const out: { label: string; url: string }[] = []
    for (let i = messages.length - 1; i >= 0 && out.length < 3; i--) {
      const m = messages[i]
      if (!m) continue
      for (let j = (m.artifacts ?? []).length - 1; j >= 0; j--) {
        const a = m.artifacts?.[j]
        if (!a?.filename || out.some((x) => x.label === a.filename)) continue
        out.push({ label: a.filename, url: fileUrl(a.filename) })
        if (out.length >= 3) break
      }
    }
    return out
  }, [messages])

  const menuFor = (tab: string): MenuItem[] => {
    const jump = (target: string, labelKey: string): MenuItem => ({
      label: t(labelKey),
      detail: { tab: target },
    })
    switch (tab) {
      case 'files':
      case 'preview':
        return [
          ...recentArtifacts.map<MenuItem>((a) => ({
            label: a.label,
            detail: { url: a.url },
            Icon: FileBox,
          })),
          jump(
            tab === 'files' ? 'preview' : 'files',
            tab === 'files' ? 'toolbar.preview' : 'toolbar.files',
          ),
        ]
      case 'terminal':
        return [jump('audit', 'agentPanel.tabAudit'), jump('git', 'toolbar.gitConsole')]
      case 'git':
        return [jump('terminal', 'toolbar.develop'), jump('files', 'toolbar.files')]
      default:
        return []
    }
  }

  return (
    <div
      className="relative z-overlay flex items-center justify-between gap-2 px-4 h-9 max-lg:h-11 border-b border-hairline flex-shrink-0"
      data-testid="toolbar-row"
    >
      <div
        className="flex items-center gap-0.5 min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        role="group"
        aria-label={t('toolbar.group')}
      >
        {TOOLS.map(({ tab, labelKey, Icon }) => (
          <div key={tab} className="inline-flex items-center rounded-md shrink-0 max-lg:min-w-11">
            <button
              onClick={() => openTab(tab)}
              aria-label={t(labelKey)}
              title={t(labelKey)}
              data-testid={`toolbar-${tab}`}
              aria-current={activeTab === tab || undefined}
              className={`inline-flex items-center justify-center gap-1 rounded-md pl-1.5 pr-0.5 py-1 text-ui-sm transition-colors whitespace-nowrap min-w-0 min-h-6 max-lg:min-h-11 max-lg:flex-col max-lg:gap-0.5 max-lg:px-1 ${
                activeTab === tab
                  ? 'text-brand bg-brand/10'
                  : 'text-ink-soft hover:text-foreground/80 hover:bg-surface-interactive'
              }`}
            >
              <Icon
                className={`h-3.5 w-3.5 ${activeTab === tab ? 'text-brand' : 'text-brand/40'}`}
                aria-hidden="true"
              />
              {/* Below md the word sits under the glyph instead of beside it. The
                  first cut dropped the label entirely to make five tools fit 390 px
                  — measured, that left five anonymous menus, because a tooltip
                  never renders on a phone. Stacking keeps the same width per chip. */}
              <span className="md:inline truncate min-w-0 max-lg:text-ui-2xs max-lg:leading-none">
                {t(labelKey)}
              </span>
            </button>
            <button
              type="button"
              data-testid={`toolbar-${tab}-menu`}
              aria-haspopup="menu"
              aria-expanded={menu?.tab === tab || undefined}
              aria-label={t('toolbar.menu', { tab: t(labelKey) })}
              title={t('toolbar.menu', { tab: t(labelKey) })}
              onClick={(e) => {
                const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
                setMenu((prev) => (prev?.tab === tab ? null : { tab, rect: r }))
              }}
              className={`inline-flex items-center justify-center min-w-6 min-h-6 rounded-md px-0.5 py-1 text-ink-faint hover:text-foreground/80 hover:bg-surface-interactive transition-colors ${
                menu?.tab === tab ? 'text-foreground/90 bg-surface-interactive' : ''
              }`}
            >
              {/* The caret is an icon node of the row's own 14 px step. As a
                  `text-ui-2xs` character it measured 8.8 x 21 px at 1440 px
                  beside 14 px chip icons — the row's one glyph size, and the
                  24 px target floor, are the same edit. */}
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
      {/* R39: Palette-Button rechts in Zeile 2 — Meta-Werte wohnen im Header */}
      <button
        onClick={() =>
          window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))
        }
        aria-label={t('chat.openPalette')}
        title={t('chat.openPalette')}
        data-testid="toolbar-palette"
        className="hidden md:inline-flex items-center gap-1 min-h-6 rounded-md px-1.5 py-0.5 text-ui-xs text-ink-faint hover:text-foreground/80 hover:bg-surface-interactive transition-colors whitespace-nowrap shrink-0"
      >
        <span className="tabular-nums">⌘K</span>
        <span>{t('toolbar.palette')}</span>
      </button>
      {menu &&
        createPortal(
          <>
            <div
              className="fixed inset-0 z-modal"
              aria-hidden="true"
              onClick={() => setMenu(null)}
            />
            <div
              data-testid={`toolbar-dropdown-${menu.tab}`}
              role="menu"
              style={{ position: 'fixed', top: menu.rect.bottom + 6, left: menu.rect.left }}
              className="z-modal min-w-56 max-w-80 float-surface p-1"
            >
              {menuFor(menu.tab).map((item, i) => (
                <button
                  key={i}
                  type="button"
                  role="menuitem"
                  data-testid={`toolbar-menu-item-${i}`}
                  onClick={() => {
                    if (!item.detail) return
                    if ('tab' in item.detail) openTab(item.detail.tab)
                    else openArtifact(item.detail.url)
                  }}
                  className="w-full text-left flex items-center gap-2 rounded-lg px-2 py-1.5 text-ui-xs text-foreground/80 hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
                >
                  {item.Icon ? (
                    <item.Icon className="h-3.5 w-3.5 shrink-0 text-brand/50" aria-hidden="true" />
                  ) : (
                    <ChevronRight
                      className="h-3.5 w-3.5 shrink-0 text-ink-faint"
                      aria-hidden="true"
                    />
                  )}
                  <span className="flex-1 min-w-0 truncate">{item.label}</span>
                </button>
              ))}
              {menuFor(menu.tab).length === 0 && (
                <p className="px-2 py-1.5 text-ui-xs text-ink-faint">{t('toolbar.menuEmpty')}</p>
              )}
            </div>
          </>,
          document.body,
        )}
    </div>
  )
}
