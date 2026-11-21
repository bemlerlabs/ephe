import { useRef, useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useChatStore } from '@/store/chatStore'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { TAB_KEYS } from '@/components/dashboard/agent/primitives'
import { searchSessionContent, fileUrl, type SessionSearchResult } from '@/lib/api'
import { openExternally } from '@/lib/nativeBrowser'
import type { CommandItem } from './paletteTypes'
import { requestSettingsOpen } from '@/lib/openSettings'
import {
  buildArtifactCommands,
  buildControlCommands,
  buildSettingsCommands,
} from './paletteExtraItems'
import {
  bumpFreq,
  fuzzyScore,
  groupBySection,
  isPaletteToggle,
  readFrecency,
  readFreq,
} from './paletteScoring'

// Public re-exports: existing import sites and unit tests stay stable.
export { bumpFreq, fuzzyScore, isPaletteToggle, readFreq }

export type { CommandItem }

/** R25: Prefix for full-text search over messages ("content:api key"). */
export const CONTENT_SEARCH_PREFIX = 'content:'

export function useCommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [contentResults, setContentResults] = useState<SessionSearchResult[]>([])
  const [contentSearching, setContentSearching] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { createSession } = useChatStore()

  const contentMode = query.toLowerCase().startsWith(CONTENT_SEARCH_PREFIX)

  // Keyboard shortcut: Ctrl/Cmd+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (isPaletteToggle(e)) {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      // Round G3 (reference parity): ⌘N = new task (sidebar row + palette).
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'n') {
        const target = e.target as HTMLElement | null
        if (
          target &&
          (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
        )
          return
        e.preventDefault()
        useChatStore.getState().createSession()
      }
      if (e.key === 'Escape' && open) {
        setOpen(false)
      }
      // P0-2: the ONLY source of the ⌘1–⌘9 panel-tab binding (Ctrl on Win/Linux).
      // The order is TAB_KEYS itself (preview,terminal,git,tasks,files,
      // audit,trajectory,subagents,memory,side) — no second, diverging array
      // anymore. `toggle:true` uses the toggle path of the panel listener: pressing
      // again closes the active tab. Panel focus stays ⌘O / ⌥⌘B.
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
        // WP5: the digit keys are all taken — ⌘0 is the tenth page (as in a
        // browser), so a tab added later never becomes unreachable.
        const n = e.key === '0' ? TAB_KEYS.length : Number(e.key)
        if (Number.isInteger(n) && n >= 1 && n <= TAB_KEYS.length) {
          const target = e.target as HTMLElement | null
          if (
            target &&
            (target.tagName === 'INPUT' ||
              target.tagName === 'TEXTAREA' ||
              target.isContentEditable)
          )
            return
          e.preventDefault()
          window.dispatchEvent(
            new CustomEvent(PREVIEW_OPEN_EVENT, {
              detail: { tab: TAB_KEYS[n - 1], toggle: true },
            }),
          )
        } else if (e.key.toLowerCase() === 'o') {
          const target = e.target as HTMLElement | null
          if (
            target &&
            (target.tagName === 'INPUT' ||
              target.tagName === 'TEXTAREA' ||
              target.isContentEditable)
          )
            return
          e.preventDefault()
          window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
        }
      }
      // P2-A (Ephe norm "toggle panel ⌥ ⌘ B"): collapse/expand the panel —
      // the same toggle detail path as ⌘⇧O, but with Alt instead of Shift so
      // it never collides with ⌘B (the sidebar).
      if ((e.metaKey || e.ctrlKey) && e.altKey && e.key.toLowerCase() === 'b') {
        const target = e.target as HTMLElement | null
        if (
          target &&
          (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
        )
          return
        e.preventDefault()
        window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }))
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
    } else {
      setQuery('')
    }
  }, [open])

  // R25: "content:…" → debounced full-text search over all sessions (backend FTS5)
  useEffect(() => {
    if (!contentMode) {
      setContentResults([])
      setContentSearching(false)
      return
    }
    const term = query.slice(CONTENT_SEARCH_PREFIX.length).trim()
    if (term.length < 2) {
      setContentResults([])
      setContentSearching(false)
      return
    }
    setContentSearching(true)
    // P1-10: a newer query aborts the in-flight request (clearTimeout only
    // dropped the timer, so a fast typist's earlier hit could still land).
    const controller = new AbortController()
    const handle = setTimeout(async () => {
      try {
        const res = await searchSessionContent(term, 12, controller.signal)
        setContentResults(res.results)
      } catch {
        if (!controller.signal.aborted) setContentResults([]) // aborted or unreachable
      } finally {
        if (!controller.signal.aborted) setContentSearching(false)
      }
    }, 250)
    return () => {
      clearTimeout(handle)
      controller.abort()
    }
  }, [contentMode, query])

  const commands: CommandItem[] = [
    {
      id: 'chat',
      label: t('commandPalette.items.chat'),
      section: t('commandPalette.sections.pages'),
      action: () => {
        navigate('/')
        setOpen(false)
      },
    },
    {
      id: 'new-session',
      label: t('commandPalette.items.newSession'),
      section: t('commandPalette.sections.sessions'),
      shortcutId: 'new',
      action: () => {
        createSession()
        setOpen(false)
      },
    },
    {
      id: 'settings',
      label: t('commandPalette.items.settings'),
      section: t('commandPalette.sections.settings'),
      // Toggle inventory 2026-09-07: this was a no-op (only setOpen(false)). The
      // ChatLayout listener on 'ephe:open-settings' is the central entry — with the
      // header gear gone, the palette is the second way into settings.
      action: () => {
        // The hub lives with the chat shell; from another page the request carries
        // through the route change instead of firing into a page without a listener.
        requestSettingsOpen()
        setOpen(false)
      },
    },
    // Dictionary 2026-10-06 (R4): the palette had TWO entries for the same
    // action — "open live preview" (id preview) and "open browser"
    // (id panel-browser). One of them is gone; the one that stays names the thing
    // after the surface: Browser. `commandPalette.items.preview` lives on as the
    // title of the browser frame (previewFrame.tsx), not as a palette entry.
    // Round 12: panel tabs + sidebar + dock + workspace (AI-client parity).
    // P2-A: 'browser' follows the same pattern — a label with its own defaultValue.
    ...(['terminal', 'git', 'files', 'subagents', 'browser'] as const).map((tab) => ({
      id: `panel-${tab}`,
      shortcutId: 'panelTabs' as const, // P1-16: the digit row reaches the same tabs
      label: t(
        `commandPalette.items.panel_${tab}`,
        tab === 'browser' ? { defaultValue: 'Open browser' } : { defaultValue: `Open ${tab}` },
      ),
      section: t('commandPalette.sections.agentPanel', { defaultValue: 'Agent panel' }),
      action: () => {
        window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
        setOpen(false)
      },
    })),
    {
      id: 'sidebar-toggle',
      label: t('commandPalette.items.sidebarToggle', { defaultValue: 'Toggle sidebar' }),
      section: t('commandPalette.sections.view', { defaultValue: 'View' }),
      shortcutId: 'sidebar',
      action: () => {
        window.dispatchEvent(new CustomEvent('ephe:toggle-sidebar'))
        setOpen(false)
      },
    },
    {
      id: 'panel-dock-toggle',
      label: t('commandPalette.items.panelDock', {
        defaultValue: 'Switch panel side (left/right)',
      }),
      section: t('commandPalette.sections.view', { defaultValue: 'View' }),
      shortcutId: 'panelDock',
      action: () => {
        window.dispatchEvent(new CustomEvent('ephe:panel-dock-toggle'))
        setOpen(false)
      },
    },
    {
      id: 'workspace-switch',
      label: t('commandPalette.items.workspace', { defaultValue: 'Switch workspace' }),
      section: t('commandPalette.sections.settings'),
      // Honest purpose: the workspace folder lives in the Engine tab of the
      // settings (input + folder picker). Before, this entry opened the settings
      // blindly on the last active tab.
      action: () => {
        window.dispatchEvent(new CustomEvent('ephe:open-settings'))
        window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'engine' } }))
        setOpen(false)
      },
    },
    {
      id: 'github',
      label: t('commandPalette.items.github'),
      section: t('commandPalette.sections.pages'),
      action: () => {
        // W10 (FINDINGS 2026-10-12): raw window.open is a no-op in the Tauri shell —
        // there is no window to open into. openExternally is the shell's working path
        // (browser_open_external) and keeps window.open for the PWA.
        void openExternally('https://github.com/bemlerlabs/ephe')
        setOpen(false)
      },
    },
    {
      id: 'docs',
      label: t('commandPalette.items.docs'),
      section: t('commandPalette.sections.pages'),
      action: () => {
        void openExternally('https://ephe.app/docs')
        setOpen(false)
      },
    },
  ]

  // Load recent sessions for search
  const sessions = useChatStore.getState().sessions
  const sessionCommands: CommandItem[] = sessions.slice(0, 5).map((s) => ({
    id: `session-${s.id}`,
    label: s.title,
    section: t('commandPalette.sections.sessions'),
    action: () => {
      useChatStore.getState().setActiveSession(s.id)
      navigate('/chat')
      setOpen(false)
    },
  }))

  // P1 [F5] "open artifact": the most recent artifacts of the active session as
  // a direct action (click → preview tab). Newest first, deduplicated, max. 5.
  const currentSession = useChatStore.getState().currentSession
  const seenFilenames = new Set<string>()
  const artifactFilenames: string[] = []
  const msgs = currentSession?.messages ?? []
  for (let i = msgs.length - 1; i >= 0 && artifactFilenames.length < 5; i--) {
    const m = msgs[i]
    if (!m) continue
    for (const a of m.artifacts ?? []) {
      if (!a?.filename || seenFilenames.has(a.filename)) continue
      seenFilenames.add(a.filename)
      artifactFilenames.push(a.filename)
    }
  }
  const artifactCommands = buildArtifactCommands({
    filenames: artifactFilenames,
    fileUrl,
    sectionLabel: t('commandPalette.sections.artifacts', { defaultValue: 'Artifacts' }),
    open: (url) => {
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url } }))
      setOpen(false)
    },
  })

  // P1 [F5] settings sub-pages: the panel's own NAV (settings/model.tsx) as palette
  // entries — reference parity of "jump to a setting" instead of only opening
  // settings blind. W10: the list is DERIVED in paletteExtraItems from that NAV, so a
  // tab the panel grows is addressable here in the same change.
  const settingsCommands = buildSettingsCommands({
    label: (key) => t(`settings.${key}`),
    sectionLabel: t('commandPalette.sections.settings'),
    openTab: (tab) => {
      window.dispatchEvent(new CustomEvent('ephe:open-settings'))
      window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab } }))
      setOpen(false)
    },
  })

  // W10 (FINDINGS 2026-10-12, medium): "the palette reaches a tab, never a control."
  // Under a query the panel's row index joins the list; a hit opens the row's tab and
  // hands the row's own label to the panel's search, which then names the control.
  // Without a query the curated list stays as it was — the row index would drown it.
  const controlCommands = query
    ? buildControlCommands({
        label: (key) => t(key),
        sectionLabel: t('commandPalette.sections.settings'),
        openControl: (tab, rowQuery) => {
          window.dispatchEvent(new CustomEvent('ephe:open-settings'))
          window.dispatchEvent(
            new CustomEvent('ephe:settings-tab', { detail: { tab, query: rowQuery } }),
          )
          setOpen(false)
        },
      })
    : []

  const allCommands = [
    ...sessionCommands,
    ...artifactCommands,
    ...commands,
    ...settingsCommands,
    ...controlCommands,
  ]

  // R25: in content mode the full-text hits replace the command list
  const contentCommands: CommandItem[] = contentMode
    ? contentResults.map((r) => ({
        id: `content-${r.session_id}-${r.role}`,
        label: r.session_title,
        hint: `‹${r.role}› ${r.snippet.replace(/‹|›|…/g, '')}`,
        section: t('commandPalette.sections.content'),
        action: () => {
          useChatStore.getState().setActiveSession(r.session_id)
          navigate('/chat')
          setOpen(false)
        },
      }))
    : []

  const filteredCommands = contentMode
    ? contentCommands
    : query
      ? allCommands
          .map((c) => ({ c, score: fuzzyScore(c, query) }))
          .filter((x) => x.score > 0)
          .sort((a, b) => b.score - a.score)
          .map((x) => x.c)
      : allCommands

  // R63: each section leads with its best match. The rank key keeps the fuzzy
  // tiers dominant and lets only the decayed frecency break ties between equals.
  const grouped = groupBySection(filteredCommands, query, readFrecency())

  // Counts one command execution (called from App.tsx onSelect — one central place).
  const recordUsage = (id: string) => bumpFreq(id)

  return {
    open,
    setOpen,
    query,
    setQuery,
    inputRef,
    grouped,
    t,
    recordUsage,
    contentMode,
    contentSearching,
    contentResults,
  }
}
