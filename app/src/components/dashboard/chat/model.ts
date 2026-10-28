import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useVirtualizer, observeElementRect, observeElementOffset } from '@tanstack/react-virtual'
import { useChatStore, DEFAULT_SESSION_TITLE, DEFAULT_COMPOSER_MODE } from '@/store/chatStore'
import { takeChatSeed } from '@/lib/chatSeed'
import {
  listSchedules,
  createSchedule,
  deleteSchedule,
  type ScheduleJob,
  approveSandbox as approveSandboxApi,
  answerAsk as answerAskApi,
  healthCheck,
  getSettings,
  getContextStages,
  getLearningProposals,
  acceptLearningProposal,
  dismissLearningProposal,
  listSkills,
  getModelProviders,
  getMemoryStats,
  listGitBranches,
  checkoutGitBranch,
} from '@/lib/api'
import { streamChat } from '@/lib/stream'
import { remeasureRows } from '@/lib/remeasureRows'
import { humanizeStreamError, isNetworkLikeError, streamErrorCode } from '@/lib/streamErrors'
import type { TabKey } from '@/components/dashboard/settings/types'
import { applyStreamEvent } from '@/lib/streamActions'
import { estimateContextUsage, WARN_THRESHOLD } from '@/lib/contextMeter'
import { PREVIEW_OPEN_EVENT, PANEL_STATE_EVENT, QUERY_JUMP_EVENT } from '@/lib/panelEvents'
import { createChunkBatcher } from '@/lib/chunkBatcher'
import { ToolCall } from '@/types'
import { useTranslation } from 'react-i18next'
import { useTauriWindow } from '@/hooks/useTauriWindow'
import { useTauriTray } from '@/hooks/useTauriTray'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useShortcutDispatch } from '@/hooks/useShortcutDispatch'
import {
  describeSkill,
  parseSlashCommand,
  SLASH_COMMANDS,
  buildHelpText,
} from '@/lib/slashCommands'
import { compositePayload, compositeImages, type ChatAttachment } from '@/lib/attachments'
import { toastBus } from '@/lib/toast'
import { toggleCompanionEnabled } from '@/lib/companionToggle'
import { SHORTCUTS_EVENT } from '../ShortcutOverlay'
import { apiUrl } from '@/lib/api/http'

/**
 * Chat layout (PWA-Chat-UX-Plan, Phase C1/C2).
 *
 * C1 — SSE rewiring: no WebSocket anymore. Answers arrive via
 *      POST /api/chat/stream (streamChat) → applyStreamEvent → store actions
 *      (exactly 1 growing assistant bubble per turn). Tool approval runs via
 *      POST /api/sandbox/approve (token-based, no auto-approve).
 * C2 — Sessions: initFromDb() loads the sessions persisted in IndexedDB on
 *      mount (active highlight + a11y live in the Sidebar).
 */

export function useChatLayoutModel() {
  const { t } = useTranslation()
  const { isTauri, minimize, maximize } = useTauriWindow()
  const { windowVisible } = useTauriTray()
  const {
    currentSession,
    sessions,
    isTyping,
    createSession,
    addMessage,
    setTyping,
    startTurn,
    compactSession,
    checkpoints,
    createCheckpoint,
    rollbackToCheckpoint,
    deleteCheckpoint,
    initFromDb,
  } = useChatStore()
  // Z37-Follow-up (2026-10-02): the header fork chip navigates to parentId via
  // setActiveSession — a no-op when the parent sits outside the 50-session
  // restore window or was deleted. Gate: show the chip only when the parent node
  // really is in the store; otherwise the click stays dead.
  const parentLoaded = !!(
    currentSession?.parentId && sessions.some((s) => s.id === currentSession.parentId)
  )
  // W10-8 (FINDINGS 2026-10-12, high): the boot restore is asynchronous, so the
  // send path has to know whether it settled yet — and the surface has to say so.
  const hydrated = useChatStore((s) => s.hydrated)
  // The language can switch while the mount effect is in flight; the ref keeps the
  // toast wording current without re-running the restore.
  const tRef = useRef(t)
  tRef.current = t
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // R17 Artifact Hub: open the ArtifactRail library mode from the header
  const [railLibraryOpen, setRailLibraryOpen] = useState(false)
  // P6 B7: added 'plugins' — the sidebar opens the marketplace tab directly.
  // 2026 IA-Sweep: TabKey union — the sidebar nav now links straight into any
  // settings cap (cron, mcp, …); 'model' stays a legacy alias and the caller
  // maps it onto 'engine'.
  const [settingsTab, setSettingsTab] = useState<TabKey | 'model'>('model')
  // Sidebar desktop collapse (KI-client style) — persisted
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('ephe-sidebar-collapsed') === '1',
  )
  const toggleSidebarCollapsed = useCallback(() => {
    setSidebarCollapsed((v) => {
      localStorage.setItem('ephe-sidebar-collapsed', v ? '0' : '1')
      return !v
    })
  }, [])

  // P1-16: ⌘B/⌘N and ⌘⇧F/⌘U/⌘J used to be two hand-written key listeners here,
  // comparing `e.key` by hand. They are rows in `lib/shortcuts.ts` now and are
  // registered further down through `useShortcutDispatch`. ⌘N is deliberately NOT
  // registered there: useCommandPalette answers it, and two listeners on one key
  // started two sessions.

  // Header chips (KI-client style): workspace name + Git branch, read-only
  const [headerMeta, setHeaderMeta] = useState<{
    workspace: string
    git: boolean
    branch: string
    dirty: number
  } | null>(null)
  // Branch dropdown on the header chip (round 12)
  const [branchMenuOpen, setBranchMenuOpen] = useState(false)
  const [branchList, setBranchList] = useState<string[]>([])
  const [branchBusy, setBranchBusy] = useState(false)
  // Welcome action cards fill the main composer (the old Smart-Suggestions
  // box was removed) — parent-owned nonce so re-clicking a card re-seeds.
  const composerSeedNonce = useRef(0)
  const [composerSeed, setComposerSeed] = useState<{ text: string; nonce: number } | null>(null)
  const fillComposer = useCallback((text: string) => {
    composerSeedNonce.current += 1
    setComposerSeed({ text, nonce: composerSeedNonce.current })
    requestAnimationFrame(() => document.getElementById('ephe-chat-input')?.focus())
  }, [])

  // A marketplace or skill card hands over a prepared example before this route
  // mounts. It opens a fresh session, so the probe never lands in the transcript
  // the user was reading.
  useEffect(() => {
    if (!hydrated) return
    const seed = takeChatSeed()
    if (!seed) return
    createSession()
    fillComposer(seed)
  }, [hydrated, createSession, fillComposer])

  // I6 (findings line 25): after "new session" the caret belongs in the composer
  // (reference-client parity). Fires on ACTIVE-SESSION SWITCH only — never on mount,
  // so app start does not pop the mobile keyboard.
  const activeSessionId = useChatStore((s) => s.activeSessionId)
  const prevActiveSessionRef = useRef<string | null>(null)
  useEffect(() => {
    if (prevActiveSessionRef.current !== null && prevActiveSessionRef.current !== activeSessionId) {
      // Direct focus: the composer textarea is committed before effects run, so no
      // rAF round-trip is needed (and jsdom never fires rAF while hidden).
      document.getElementById('ephe-chat-input')?.focus()
      requestAnimationFrame(() => document.getElementById('ephe-chat-input')?.focus())
    }
    prevActiveSessionRef.current = activeSessionId
  }, [activeSessionId])
  const refreshHeaderMeta = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/git/info'))
      if (res.ok) setHeaderMeta(await res.json())
    } catch {
      /* Offline: leave the chips exactly as they are */
    }
  }, [])
  const toggleBranchMenu = useCallback(async () => {
    const next = !branchMenuOpen
    setBranchMenuOpen(next)
    if (!next) return
    try {
      const info = await listGitBranches()
      setBranchList(info.branches)
    } catch {
      setBranchList([])
    }
  }, [branchMenuOpen])
  const switchBranch = useCallback(
    async (branch: string) => {
      if (branchBusy || branch === headerMeta?.branch) {
        setBranchMenuOpen(false)
        return
      }
      if (
        headerMeta &&
        headerMeta.dirty > 0 &&
        !window.confirm(t('header.checkoutDirtyConfirm', { count: headerMeta.dirty }))
      ) {
        setBranchMenuOpen(false)
        return
      }
      setBranchBusy(true)
      try {
        await checkoutGitBranch(branch)
        await refreshHeaderMeta()
        setBranchMenuOpen(false)
      } catch (err) {
        toastBus.error(err instanceof Error ? err.message : t('header.checkoutFailed'))
      } finally {
        setBranchBusy(false)
      }
    },
    [branchBusy, headerMeta, refreshHeaderMeta, t],
  )
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await fetch(apiUrl('/api/git/info'))
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) setHeaderMeta(data)
      } catch {
        /* Offline: simply hide the chips */
      }
    }
    void load()
    const id = window.setInterval(load, 30_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  // ── Round 12: ←/→ back/forward between sessions (KI-client tab parity) ──────
  const navRef = useRef<{ stack: string[]; index: number }>({ stack: [], index: -1 })
  const suppressNavPushRef = useRef(false)
  const [navInfo, setNavInfo] = useState<{ canBack: boolean; canFwd: boolean }>({
    canBack: false,
    canFwd: false,
  })
  const updateNavInfo = useCallback(() => {
    const nav = navRef.current
    setNavInfo({ canBack: nav.index > 0, canFwd: nav.index < nav.stack.length - 1 })
  }, [])
  useEffect(() => {
    const id = currentSession?.id
    if (!id) return
    const nav = navRef.current
    if (suppressNavPushRef.current) {
      suppressNavPushRef.current = false
      updateNavInfo()
      return
    }
    if (nav.stack[nav.index] !== id) {
      // new branch: discard the forward history (like a browser), max 50 entries
      nav.stack = [...nav.stack.slice(0, nav.index + 1), id].slice(-50)
      nav.index = nav.stack.length - 1
    }
    updateNavInfo()
  }, [currentSession?.id, updateNavInfo])
  const navigateSession = useCallback(
    (dir: -1 | 1) => {
      const nav = navRef.current
      const next = nav.index + dir
      const target = nav.stack[next]
      if (!target) return
      nav.index = next
      suppressNavPushRef.current = true
      useChatStore.getState().setActiveSession(target)
      updateNavInfo()
    },
    [updateNavInfo],
  )

  // ── Round 12: rename the session title inline in the topbar (double-click) ─
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const startTitleEdit = useCallback(() => {
    if (!currentSession) return
    setTitleDraft(currentSession.title)
    setEditingTitle(true)
  }, [currentSession])
  const commitTitleEdit = useCallback(() => {
    setEditingTitle(false)
    const clean = titleDraft.trim()
    if (currentSession && clean && clean !== currentSession.title) {
      useChatStore.getState().renameSession(currentSession.id, clean)
    }
  }, [currentSession, titleDraft])

  // K2 (Z13): predecessor map — per row the last user message before it
  // (the prompt/response feedback pair). One pass per render, split by index.
  const prevUserAt = useMemo(() => {
    const list = currentSession?.messages ?? []
    const out: string[] = []
    let last = ''
    for (const mm of list) {
      if (mm.role === 'user') last = mm.content ?? ''
      out.push(last)
    }
    return out
  }, [currentSession?.messages])

  // Command palette actions (round 12): sidebar toggle + open settings
  useEffect(() => {
    const onToggleSidebar = () => toggleSidebarCollapsed()
    const onOpenSettings = () => setSettingsOpen(true)
    // 2026 IA-Sweep + R4-A2: the sidebar row "Artefakte" opens the **page**, not
    // the pop-up over the chat — the library is /artifacts.
    const onOpenLibrary = () => {
      window.location.hash = '#/artifacts'
    }
    window.addEventListener('ephe:toggle-sidebar', onToggleSidebar)
    window.addEventListener('ephe:open-settings', onOpenSettings)
    window.addEventListener('ephe:library-open', onOpenLibrary)
    return () => {
      window.removeEventListener('ephe:toggle-sidebar', onToggleSidebar)
      window.removeEventListener('ephe:open-settings', onOpenSettings)
      window.removeEventListener('ephe:library-open', onOpenLibrary)
    }
  }, [toggleSidebarCollapsed])

  // ── Round 14 (P3-F1): shortcut cheatsheet via ⌘/ + ⌘⇧D dock switch ────
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  // P1-16: this layout's keys, declared by table id. One dispatcher resolves them
  // (⌘B, ⌘⇧F, ⌘U, ⌘J, ⌘/, ⌘⇧D) from `lib/shortcuts.ts`, so the help overlay can
  // only ever list a key something really answers. The focus guards the removed
  // listeners carried by hand (`editable`, `inOverlay`) live on the rows now.
  useShortcutDispatch({
    sidebar: () => toggleSidebarCollapsed(),
    focusComposer: () => document.getElementById('ephe-chat-input')?.focus(),
    toggleFiles: () =>
      window.dispatchEvent(
        new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'files', toggle: true } }),
      ),
    thisOverlay: () => setShortcutsOpen((v) => !v),
    panelDock: () => window.dispatchEvent(new CustomEvent('ephe:panel-dock-toggle')),
    companion: () => void toggleCompanionEnabled(),
  })

  // The composer's hint chip opens the same overlay without a key.
  useEffect(() => {
    const onEvent = () => setShortcutsOpen((v) => !v)
    window.addEventListener(SHORTCUTS_EVENT, onEvent)
    return () => window.removeEventListener(SHORTCUTS_EVENT, onEvent)
  }, [])

  // ── C2: load sessions from IndexedDB (once, on mount) ──────────────
  useEffect(() => {
    // W10-8 (FINDINGS 2026-10-12, high): a cold open settles on ANOTHER task's
    // restored transcript (~50 rows) and no surface said so. Disclose both halves
    // of the moment — the restore that is running, and the restore that happened.
    const before = useChatStore.getState().sessions.length
    if (before === 0 && !useChatStore.getState().hydrated) {
      toastBus.info(tRef.current('chat.restoringHistory'), undefined, undefined, 'history-restore')
    }
    void initFromDb().then(() => {
      const restored = useChatStore.getState().sessions
      if (before === 0 && restored.length > 0) {
        const messages = restored.reduce((sum, s) => sum + s.messages.length, 0)
        toastBus.info(
          tRef.current('chat.historyRestored', { count: messages }),
          undefined,
          undefined,
          'history-restore',
        )
      }
    })
  }, [initFromDb])

  // ── Backend/engine reachability (header indicator, F-02 3-state) ─────
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null)
  const wasOnlineRef = useRef<boolean | null>(null)
  useEffect(() => {
    let cancelled = false
    const check = async () => {
      let ok = false
      let engine: boolean | null = null
      try {
        const info = await healthCheck()
        ok = true
        // F-02: engine_online comes from the real backend probe; for
        // local_ollama it mirrors `ollama`. null = the backend says nothing.
        engine =
          info.engine_online ?? (info.active_provider === 'local_ollama' ? info.ollama : null)
      } catch {
        ok = false
      }
      if (cancelled) return
      // G4: online → offline transition → toast (once per transition)
      if (ok === false && wasOnlineRef.current === true) {
        toastBus.error(t('chat.offline'))
      }
      wasOnlineRef.current = ok
      setBackendOnline(ok)
      setEngineOnline(engine)
    }
    check()
    const interval = setInterval(check, 10000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [t])

  // ── Round 5: toggle panel — receive the AgentPanel state ──────
  // (The header now drives ONE side-panel toggle; the active-tab display is done
  // by the panel's own tab bar. width/dock travel along so that the content
  // column gives the width back when the panel is open — split instead of
  // overlay, otherwise the panel covers the send button and the model chips.)
  const [panelGeo, setPanelGeo] = useState<{
    open: boolean
    width: number
    dock: 'left' | 'right'
  }>({ open: false, width: 560, dock: 'right' })
  const panelOpen = panelGeo.open
  const isDesktop = useMediaQuery('(min-width: 1024px)')
  const panelInset = panelOpen && isDesktop ? Math.min(panelGeo.width, 920) : 0
  useEffect(() => {
    const onState = (e: Event) => {
      const d = (
        e as CustomEvent<{ open: boolean; tab: string; width?: number; dock?: 'left' | 'right' }>
      ).detail
      setPanelGeo({
        open: !!d?.open,
        width: typeof d?.width === 'number' && d.width > 0 ? d.width : 560,
        dock: d?.dock === 'left' ? 'left' : 'right',
      })
    }
    window.addEventListener(PANEL_STATE_EVENT, onState)
    return () => window.removeEventListener(PANEL_STATE_EVENT, onState)
  }, [])

  // P0-2: the ⌘1–⌘9 panel-tab binding now lives ONCE in useCommandPalette
  // (single source of truth over TAB_KEYS). The earlier second listener here
  // fired twice per keypress with a diverging tab list (5 instead of 9) and
  // different toggle semantics → open-then-collapse flicker. Removed.

  // DD-20: ←/→ page through sessions like the header arrows — reachable by click
  // only until now. Inside text fields, menus (Dialog/Menu) and with modifier
  // keys held, the arrows are left to the normal focus/scroll behaviour.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const el = document.activeElement
      const tag = el?.tagName ?? ''
      const editable =
        tag === 'input' ||
        tag === 'textarea' ||
        (el instanceof HTMLElement && el.isContentEditable === true)
      const inOverlay =
        el instanceof HTMLElement &&
        Boolean(el.closest('[role="dialog"], [role="menu"], [role="listbox"], [role="tablist"]'))
      if (editable || inOverlay) return
      navigateSession(e.key === 'ArrowLeft' ? -1 : 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigateSession])
  // ── R26: live system gauges for the top bar (CPU/Mem/Disk, psutil) ────────
  // R39 (P2, 1:1 reference): the model chip now lives ONLY once in the composer
  // (model-chip in ChatInput) — the header duplicate (header-model-chip) is
  // removed. The meta values (uptime / free / auto read-aloud) move out of
  // toolbar-meta into the header's right-hand icon island; row 2 therefore
  // carries only the five tab buttons + ⌘K palette.
  const openPaletteFromHeader = () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))
  }

  // ── Context window of the active engine (StatusBar; vLLM max_model_len) ────
  const [contextWindow, setContextWindow] = useState<number | undefined>()
  // P1b (Deep-Audit 2026-09-16): the fetch hung on an empty dep list
  // (mount only) — after a model/provider switch the window stuck at the old
  // value. A shared 'ephe:model-changed' event (dispatched by
  // ChatInput.pickProvider) triggers the re-fetch.
  useEffect(() => {
    let cancelled = false
    const load = () =>
      getModelProviders()
        .then((r) => {
          if (!cancelled) setContextWindow(r.context_window ?? undefined)
        })
        .catch(() => {}) // backend offline -> frontend default
    load()
    const onModelChanged = () => load()
    window.addEventListener('ephe:model-changed', onModelChanged)
    return () => {
      cancelled = true
      window.removeEventListener('ephe:model-changed', onModelChanged)
    }
  }, [])

  // ── F round 4: auto-compact at the warning threshold (summary bubble) ──
  const autoCompactDoneRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    const store = useChatStore.getState()
    const session = store.currentSession
    if (!session || session.messages.length === 0 || store.isTyping) return
    const usage = estimateContextUsage(session.messages, contextWindow)
    if (usage.percent / 100 >= WARN_THRESHOLD && !autoCompactDoneRef.current.has(session.id)) {
      autoCompactDoneRef.current.add(session.id)
      compactSession()
      store.addMessage('system', t('chat.autoCompacted'))
    }
  }, [currentSession?.messages, contextWindow, compactSession, addMessage, t, isTyping])

  // ── Scheduler (P2-8) ──────────────────────────────────────────────────────
  const [scheduleJobs, setScheduleJobs] = useState<ScheduleJob[]>([])
  const loadJobs = useCallback(async () => {
    try {
      const res = await listSchedules()
      setScheduleJobs(res.jobs ?? [])
    } catch {
      // backend offline → the scheduler UI stays empty
      setScheduleJobs([])
    }
  }, [])
  useEffect(() => {
    loadJobs()
  }, [loadJobs])
  const handleScheduleCreate = useCallback(
    async (task: string, cron: string) => {
      try {
        await createSchedule(task, cron)
        await loadJobs()
        toastBus.success(t('chat.schedCreated'))
      } catch {
        // G4: surface the error (the form stays open for a retry)
        toastBus.error(t('chat.schedCreateFailed'))
      }
    },
    [loadJobs, t],
  )
  const handleScheduleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteSchedule(id)
        await loadJobs()
      } catch {
        // G4: surface the error
        toastBus.error(t('chat.schedDeleteFailed'))
      }
    },
    [loadJobs, t],
  )

  // Window hidden (minimize-to-tray) → dismiss overlays
  useEffect(() => {
    if (!windowVisible) {
      setSidebarOpen(false)
      setSettingsOpen(false)
    }
  }, [windowVisible])

  const [railActive, setRailActive] = useState(-1)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  // G1.4: pinned-bottom detection — auto-scroll only when the user is at the
  // end; otherwise a floating scroll-down button instead of a scroll fight.
  const [isPinned, setIsPinned] = useState(true)
  const isPinnedRef = useRef(true)

  // ── C1: abort controller for the current SSE stream ──────────────────
  const abortRef = useRef<AbortController | null>(null)
  // G1.2: the last failed turn (message id + payload) for retry
  const failedTurnRef = useRef<{ messageId: string; payload: string; images?: string[] } | null>(
    null,
  )
  // W10-8: sends that arrived while the boot restore was still running, in order.
  // A queue, not a slot — two sends must not overwrite each other into silence.
  const pendingBootSendRef = useRef<
    { sessionId: string | null; message: string; attachments: ChatAttachment[] }[]
  >([])

  // P1-5: unmount parity — a fetch reader that was never closed would keep
  // running after the panel is swapped out and write chunks into the old instance.
  useEffect(
    () => () => {
      abortRef.current?.abort()
    },
    [],
  )

  // Virtualization — only render visible messages
  const parentRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: currentSession?.messages.length ?? 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 120,
    overscan: 6,
    // W33: stable node->index assignment keyed by the message id (not the array
    // index). When appending/revising, measurements travel with their message
    // instead of shifting -> fewer scroll jumps.
    getItemKey: (index: number) => currentSession?.messages[index]?.id ?? index,
    // A ResizeObserver per node: tall/recalculating cards (tables, think-expand,
    // images) are re-measured after the first measurement → no cumulative
    // top-drift, no overlapping rows.
    observeElementRect,
    observeElementOffset,
  })

  // Timeline rail: clicking a marker scrolls to the message; scrolling updates activeIndex
  const handleRailSelect = useCallback(
    (index: number) => {
      setRailActive(index)
      rowVirtualizer.scrollToIndex(index, { align: 'start' })
    },
    [rowVirtualizer],
  )

  // [F9] Query map: the jump comes out of the agent-status panel ("Jump to
  // query N") as a window event — here map the message id onto its virtualizer
  // index and scroll as if the rail had been selected.
  useEffect(() => {
    const onQueryJump = (e: Event) => {
      const messageId = (e as CustomEvent<{ messageId?: string }>).detail?.messageId
      if (!messageId) return
      const msgs = currentSession?.messages ?? []
      const idx = msgs.findIndex((m) => m.id === messageId)
      if (idx >= 0) handleRailSelect(idx)
    }
    window.addEventListener(QUERY_JUMP_EVENT, onQueryJump)
    return () => window.removeEventListener(QUERY_JUMP_EVENT, onQueryJump)
  }, [currentSession?.messages, handleRailSelect])

  const handleScroll = useCallback(() => {
    const first = rowVirtualizer.getVirtualItems()[0]
    if (first) setRailActive(first.index)
    // G1.4: pinned = within ~40px of the end
    const el = parentRef.current
    if (el) {
      const pinned = el.scrollTop + el.clientHeight >= el.scrollHeight - 40
      isPinnedRef.current = pinned
      setIsPinned(pinned)
    }
  }, [rowVirtualizer])

  // G1.4: sending a user message / jumping in the timeline → always pin to bottom.
  // F-04: deliberately 'auto' (instant) instead of 'smooth' — repeated smooth
  // scrolls cancel each other and end visibly SOMEWHERE above the bottom.
  // Root-cause fix for auto-scroll: messagesEndRef sits OUTSIDE the overflow-y-auto
  // container (parentRef) — scrollIntoView on the sentinel scrolled the wrong
  // container, the virtualizer container never followed the growing last message.
  // Setting parentRef.scrollTop directly to scrollHeight is the only way that
  // hits the real scroll container.
  const scrollToBottom = useCallback(() => {
    const el = parentRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  const pinToBottom = useCallback(() => {
    isPinnedRef.current = true
    setIsPinned(true)
    requestAnimationFrame(scrollToBottom)
  }, [scrollToBottom])

  // Auto-scroll on new messages — ONLY when pinned (G1.4: reading the history is
  // no longer yanked around by auto-scroll).
  useEffect(() => {
    if (isPinnedRef.current) {
      requestAnimationFrame(scrollToBottom)
    }
  }, [currentSession?.messages, scrollToBottom])

  // G1.6: after turn end (streaming → done) re-measure every row — the Markdown
  // heights changed while streaming (estimateSize 120 was only an estimate),
  // otherwise the scroll jumps on the next virtual render.
  const wasTypingRef = useRef(false)
  useEffect(() => {
    if (wasTypingRef.current && !isTyping) {
      rowVirtualizer.measure()
      // R36-B: measure() only clears the size cache — already-mounted rows are
      // NOT re-measured (the measureElement ref is not re-invoked, the
      // ResizeObserver stays silent without a resize). Heights that changed
      // while the stream auto-scrolled stayed at the estimateSize and rows
      // overlapped their neighbours. Feed the cache explicitly.
      //
      // Two passes: measureElement → resizeItem is gated while the virtualizer
      // still considers us scrolling (the turn-end pin-to-bottom scroll), so
      // the first pass can be a no-op. The second pass runs after the scroll
      // grace window and always lands the real heights.
      const remeasurePass = () => {
        remeasureRows(parentRef.current, '[data-testid="message-row"]', (el) =>
          rowVirtualizer.measureElement(el),
        )
        // F-04: after re-measuring the list can be shorter/longer — if we were
        // pinned, guarantee the end again (otherwise the last answer hangs down
        // behind the composer).
        if (isPinnedRef.current) {
          requestAnimationFrame(scrollToBottom)
        }
      }
      const raf = requestAnimationFrame(remeasurePass)
      // 220ms > isScrollingResetDelay (150ms) after pass 1's own pin-scroll.
      const secondPass = setTimeout(remeasurePass, 220)
      return () => {
        cancelAnimationFrame(raf)
        clearTimeout(secondPass)
      }
    }
    wasTypingRef.current = isTyping
  }, [isTyping, rowVirtualizer, scrollToBottom])

  // ── Phase F: Slash-Commands + Compact ────────────────────────────────────
  /** Clear the active session (/clear). */
  const clearActiveSession = useCallback(() => {
    const id = useChatStore.getState().activeSessionId
    if (!id) return
    useChatStore.setState((s) => ({
      sessions: s.sessions.map((x) => (x.id === id ? { ...x, messages: [] } : x)),
      currentSession:
        s.currentSession?.id === id ? { ...s.currentSession, messages: [] } : s.currentSession,
    }))
  }, [])

  /** /compact → compact the session; /new → new session; /clear → clear it; /help → list */
  const handleSendRef = useRef<(msg: string) => void>(() => {})
  const handleSlashCommand = useCallback(
    (raw: string) => {
      const { matched, action } = parseSlashCommand(raw)
      if (!matched || !action) {
        // Not a client command → hand it to the backend: skill triggers apply
        // there (e.g. /plan, /security-review); without a match the model sees the raw text.
        void handleSendRef.current(raw)
        return
      }
      switch (action) {
        case 'compact':
          // F-14: visible feedback — before this it was a silent no-op for the user.
          compactSession()
          addMessage('system', t('chat.compacted'))
          break
        case 'new':
          createSession()
          break
        case 'clear':
          clearActiveSession()
          break
        case 'model':
          // G6: show the current model (provider + model) from the settings
          getSettings()
            .then((s) => {
              const provider = s.provider?.type ?? '–'
              const model = s.provider?.model ?? '–'
              addMessage('system', t('chat.modelNow', { provider, model }))
            })
            .catch(() => addMessage('system', t('chat.modelUnreachable')))
          break
        case 'skills':
          // G6: list the backend skills (GET /api/skills)
          listSkills()
            .then(({ skills }) => {
              if (!skills || skills.length === 0) {
                addMessage('system', t('chat.noSkills'))
                return
              }
              const list = skills.map((s) => `• ${s.name} — ${describeSkill(s, t)}`).join('\n')
              addMessage('system', t('chat.skillList', { list }))
            })
            .catch(() => addMessage('system', t('chat.skillUnreachable')))
          break
        case 'sessions': {
          // G6: show the current sessions from the store
          const sessions = useChatStore.getState().sessions
          if (sessions.length === 0) {
            addMessage('system', t('chat.noSessions'))
          } else {
            const list = sessions
              .map(
                (s, i) =>
                  `• ${i + 1}. ${s.title === DEFAULT_SESSION_TITLE ? String(t('sidebar.newChat')) : s.title} (${s.messages.length})`,
              )
              .join('  \n') // I6 P3-1: Hartumbruch — einfaches '\n' kollabiert in Markdown
            addMessage('system', t('chat.sessionList', { list }))
          }
          break
        }
        case 'proposals':
          // R31 learning loop: show what the agent noticed and wants to learn
          getLearningProposals()
            .then(({ proposals }) => {
              if (!proposals || proposals.length === 0) {
                addMessage('system', t('chat.noProposals'))
                return
              }
              const list = proposals
                .map((pr) => `• ${pr.id} — [${pr.kind}] ${pr.topic.slice(0, 80)}`)
                .join('\n')
              addMessage('system', t('chat.proposalList', { list }))
            })
            .catch(() => addMessage('system', t('chat.proposalsUnreachable')))
          break
        case 'accept': {
          // /accept <id> — the id arrives as the command's rest argument
          const pid = raw.trim().split(/\s+/).slice(1).join('')
          if (!pid) {
            addMessage('system', t('chat.acceptNeedsId'))
            break
          }
          getSettings()
            .then((st) => acceptLearningProposal(pid, st.provider?.model ?? 'default'))
            .then((res) => addMessage('system', t('chat.acceptInstalled', { name: res.installed })))
            .catch((err: Error) =>
              addMessage('system', t('chat.acceptFailed', { reason: err?.message || 'unknown' })),
            )
          break
        }
        case 'dismiss': {
          // /dismiss <id>
          const pid = raw.trim().split(/\s+/).slice(1).join('')
          if (!pid) {
            addMessage('system', t('chat.acceptNeedsId'))
            break
          }
          dismissLearningProposal(pid)
            .then(() => addMessage('system', t('chat.dismissed', { id: pid })))
            .catch(() => addMessage('system', t('chat.proposalsUnreachable')))
          break
        }
        case 'context': {
          // R29 transparency: show which stages spoke into the system prompt
          getContextStages()
            .then(({ stages, total_chars }) => {
              if (!stages || stages.length === 0) {
                addMessage('system', t('chat.contextEmpty'))
                return
              }
              const list = stages.map((st) => `• ${st.name} — ${st.chars} chars`).join('\n')
              addMessage('system', t('chat.contextStages', { list, total: total_chars }))
            })
            .catch(() => addMessage('system', t('chat.contextUnreachable')))
          break
        }
        case 'memory':
          // /memory → print the semantic-memory statistics (vector count) in the chat
          getMemoryStats()
            .then((m) => addMessage('system', t('chat.memoryNow', { count: m.total })))
            .catch(() => addMessage('system', t('chat.memoryUnreachable')))
          break
        case 'settings':
          // G6: open the settings panel
          setSettingsOpen(true)
          break
        case 'companion':
          // QD-005: the same switch the header toggle and the chord flip.
          void toggleCompanionEnabled()
          break
        case 'personality':
          // R28: open the persona editor directly (settings panel + tab deep link)
          setSettingsOpen(true)
          window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'persona' } }))
          break
        case 'help':
          addMessage(
            'system',
            t('chat.helpList', {
              // I6 P3-1: hard line breaks + translated descriptions — before this the
              // '\n' lines collapsed into one single-line English blob.
              list: buildHelpText(SLASH_COMMANDS, (key) => String(t(key))),
            }),
          )
          break
      }
    },
    [addMessage, compactSession, createSession, t, clearActiveSession],
  )

  // ── C1: SSE send ───────────────────────────────────────────────────────
  // G1: the turn core without the user bubble — shared by handleSend (new
  // message), edit, regenerate and retry. Invariant: the LAST message of the
  // session is the user message the turn refers to (the backend appends
  // request.message to history → history = everything except the last one).
  const runTurn = useCallback(
    async (payload: string, images?: string[], isRetry = false) => {
      startTurn()
      setTyping(true)

      const s = useChatStore.getState()
      const session_ = s.currentSession
      const history = session_
        ? session_.messages.slice(0, -1).map((m) => ({ role: m.role, content: m.content }))
        : []

      // SSE stream: POST /api/chat/stream → events → store
      // D2: chunks are batched per rAF (1 set/render per frame instead of per chunk).
      const controller = new AbortController()
      abortRef.current = controller

      const batcher = createChunkBatcher({
        onFlush: (text) => useChatStore.getState().appendChunk(text),
      })
      // Store adapter: appendChunk is diverted into the batcher, all other
      // actions (zustand, stable) apply 1:1 to the real state.
      const batchedStore = {
        ...useChatStore.getState(),
        appendChunk: (data: string) => batcher.add(data),
      }

      try {
        await streamChat(
          {
            message: payload,
            history,
            session_id: session_?.id,
            mode: session_?.mode ?? DEFAULT_COMPOSER_MODE,
            // Full access → autonomous: the backend only auto-gates when
            // autonomous=True (sandbox_auto_approval_allowed). Without this field the
            // mode stays on the strict dialog even though 'full-access' was chosen.
            autonomous: (session_?.mode ?? DEFAULT_COMPOSER_MODE) === 'full-access',
            ...(images && images.length > 0 ? { images } : {}),
          },
          {
            signal: controller.signal,
            onEvent: (event) => {
              // Every NON-chunk event (activity/tool/done/error/…) flushes the batch
              // first: that way the running text lands BEFORE the next
              // phase/tool/done marker (the ordering stays consistent).
              if (event.type !== 'chunk') batcher.flush()
              applyStreamEvent(event, batchedStore)
            },
          },
        )
        // Stream closed cleanly (done) → flush the remaining chunks
        batcher.flush()
        // Stopp-Button: streamChat resolves NORMALLY after an abort (it cancels
        // the reader and returns) — the catch below never runs. Close the turn
        // here, otherwise the bubble stays streaming:true and the NEXT turn's
        // response is appended into it (deploy-check P1-1 regression).
        if (controller.signal.aborted) {
          useChatStore.getState().finishTurn()
          // A stop that landed before any content/thinking/tool output leaves an
          // empty bubble — drop it instead of shipping visual noise into history.
          const cs = useChatStore.getState().currentSession
          const last = cs?.messages[cs.messages.length - 1]
          if (
            last?.role === 'assistant' &&
            !last.content &&
            !last.thinking?.text &&
            !(last.activities && last.activities.length > 0)
          ) {
            useChatStore.getState().removeMessage(last.id)
          }
        }
      } catch (err) {
        // Always flush the buffer (also on error/abort) so no text gets lost
        // inside the batcher; only then handle error/abort.
        batcher.flush()
        if (controller.signal.aborted) {
          // Stop: the stream was aborted on purpose — close the turn cleanly
          useChatStore.getState().finishTurn()
        } else {
          // Round 9: auto-retry — pure connection errors (engine restart, Wi-Fi
          // hiccup) retry ONCE automatically after a short backoff pause;
          // everything else (4xx, abort) stays with the visible retry button.
          // DD-15: the same signature as the humanization — before this the
          // browser-side fetch TypeError (not a StreamChatError) slipped through the gate.
          const isConnectionError = isNetworkLikeError(err)
          if (isConnectionError && !isRetry) {
            const cs0 = useChatStore.getState().currentSession
            const last0 = cs0?.messages[cs0.messages.length - 1]
            if (last0?.role === 'assistant') useChatStore.getState().removeMessage(last0.id)
            await new Promise((r) => setTimeout(r, 1500))
            await runTurn(payload, images, true)
            return
          }
          const msg = humanizeStreamError(err, t)
          // DD-15: a network-like error means the server just went away — the header
          // chip must not keep claiming "Connected" until the next health poll (10s).
          // Flip immediately (including wasOnlineRef, so the next poll does not raise a
          // duplicate toast); otherwise the poll is what relativises it.
          if (isNetworkLikeError(err)) {
            setBackendOnline(false)
            wasOnlineRef.current = false
          }
          useChatStore.getState().markStreamError(msg, streamErrorCode(err))
          // G1.2: remember the failed assistant message + payload for retry
          const cs = useChatStore.getState().currentSession
          const last = cs?.messages[cs.messages.length - 1]
          if (last?.role === 'assistant') {
            failedTurnRef.current = { messageId: last.id, payload, images }
          }
        }
      } finally {
        abortRef.current = null
        setTyping(false)
      }
    },
    [startTurn, setTyping, t],
  )

  const handleSend = useCallback(
    async (message: string, attachments?: ChatAttachment[]) => {
      // Backstop: no parallel turn (the composer queue takes over while isTyping)
      if (useChatStore.getState().isTyping) return
      // P9-F1 (round 14): backend offline → do not send into the void
      if (backendOnline === false) {
        toastBus.error(t('chat.sendOffline'))
        return
      }
      // W10-8 (FINDINGS 2026-10-12, high): the boot restore is asynchronous and its
      // `set({ sessions, activeSessionId, currentSession })` replaces the whole
      // list. A send that ran before it settled wrote the bubble (and started the
      // turn) into state that was then overwritten — the text was gone from the
      // client and from the mirror (`message_lost_no_task_carries_the_sent_text`).
      // The read stays where it is; the send waits. Held, disclosed out loud and
      // replayed on hydrate — never dropped in silence.
      if (!useChatStore.getState().hydrated) {
        pendingBootSendRef.current.push({
          sessionId: useChatStore.getState().currentSession?.id ?? null,
          message,
          attachments: attachments ?? [],
        })
        toastBus.info(t('chat.restoringHistory'), t('chat.sendHeldUntilRestore'))
        return
      }
      if (!useChatStore.getState().currentSession) {
        createSession()
      }

      // G3: attachment text (code blocks + path hints) into the payload, images → images
      const payload = compositePayload(message, attachments ?? [])
      const images = compositeImages(attachments ?? [])

      // 1. user message (own bubble) → 2. exactly ONE empty assistant bubble
      addMessage('user', payload)
      failedTurnRef.current = null
      pinToBottom()
      await runTurn(payload, images)
    },
    [addMessage, createSession, runTurn, pinToBottom, backendOnline, t],
  )
  handleSendRef.current = (msg: string) => {
    void handleSend(msg)
  }

  // W10-8: replay what the boot held back — once, in order, after the restore
  // settled. The task the text was typed in wins: a task created in the still-empty
  // store is put back under its own id instead of the message being left behind in
  // the restored transcript of somebody else's task.
  useEffect(() => {
    if (!hydrated || pendingBootSendRef.current.length === 0) return
    const held = pendingBootSendRef.current.splice(0)
    void (async () => {
      for (const pending of held) {
        const store = useChatStore.getState()
        if (pending.sessionId) {
          if (!store.sessions.some((s) => s.id === pending.sessionId)) {
            const revived = {
              id: pending.sessionId,
              title: DEFAULT_SESSION_TITLE,
              messages: [],
              mode: DEFAULT_COMPOSER_MODE,
              createdAt: Date.now(),
            }
            useChatStore.setState((s) => ({
              sessions: [revived, ...s.sessions],
              activeSessionId: revived.id,
              currentSession: revived,
            }))
          }
          store.setActiveSession(pending.sessionId)
        } else {
          // Typed into a still-blank composer: the text gets its own task rather
          // than being filed into the transcript the restore just put on screen.
          store.createSession()
        }
        await handleSend(pending.message, pending.attachments)
      }
    })()
  }, [hydrated, handleSend])

  // J6: AskUserQuestion card — clicking an option sends that label directly.
  const handlePickOption = useCallback(
    (answer: string) => {
      void handleSend(answer)
    },
    [handleSend],
  )

  // G1: the live ask card — the answer goes back into the RUN THAT ASKED through
  // POST /api/ask/answer. `handlePickOption` above starts a new turn, because the
  // question it answers belongs to a finished answer; this one belongs to a turn that
  // is still open on the server, so the same run continues with it.
  const handleAnswerAsk = useCallback(async (token: string, answer: string) => {
    const store = useChatStore.getState()
    try {
      await answerAskApi(token, answer)
      store.markAskAnswered(token, answer)
    } catch {
      // 404: the run had already gone on (its timeout, or the stop button). The card
      // says what happened instead of pretending the answer landed.
      store.markAskExpired(token)
    }
  }, [])

  // ── G1.1: edit (user message) — replace the content, cut off the rest, resend
  const handleEditMessage = useCallback(
    async (id: string, newContent: string) => {
      const store = useChatStore.getState()
      if (store.isTyping) return
      store.updateMessageContent(id, newContent)
      store.truncateAfter(id)
      failedTurnRef.current = null
      await runTurn(newContent)
    },
    [runTurn],
  )

  // ── G1.1: regenerate — go back to the previous user message, cut off the rest
  const handleRegenerate = useCallback(
    async (assistantId: string) => {
      const store = useChatStore.getState()
      if (store.isTyping) return
      const msgs = store.currentSession?.messages ?? []
      const idx = msgs.findIndex((m) => m.id === assistantId)
      if (idx === -1) return
      let userIdx = -1
      for (let i = idx - 1; i >= 0; i--) {
        if (msgs[i]!.role === 'user') {
          userIdx = i
          break
        }
      }
      if (userIdx === -1) return
      const userMsg = msgs[userIdx]!
      store.truncateAfter(userMsg.id)
      failedTurnRef.current = null
      await runTurn(userMsg.content)
    },
    [runTurn],
  )

  // ── G1.2: retry — repeat a failed turn cleanly (F-09).
  // Before: a silent bail when failedTurnRef did not (still) match — the button
  // looked dead. Now: a dedicated turn-replay path (like regenerate, only
  // including the user payload/attachments from the failed turn when known).
  const handleRetry = useCallback(
    async (messageId: string) => {
      const store = useChatStore.getState()
      if (store.isTyping) return
      const failed = failedTurnRef.current
      if (failed && failed.messageId === messageId) {
        store.removeMessage(messageId)
        failedTurnRef.current = null
        pinToBottom()
        await runTurn(failed.payload, failed.images)
        return
      }
      // Fallback (ref gone — e.g. after a reload): find the user message before the
      // error bubble, cut off the rest, run again from that user message.
      const msgs = store.currentSession?.messages ?? []
      const idx = msgs.findIndex((m) => m.id === messageId)
      if (idx === -1) {
        toastBus.error(t('chat.retryUnavailable'))
        return
      }
      let userIdx = -1
      for (let i = idx - 1; i >= 0; i--) {
        if (msgs[i]!.role === 'user') {
          userIdx = i
          break
        }
      }
      if (userIdx === -1) {
        toastBus.error(t('chat.retryUnavailable'))
        return
      }
      const userMsg = msgs[userIdx]!
      store.truncateAfter(userMsg.id)
      pinToBottom()
      await runTurn(userMsg.content)
    },
    [runTurn, pinToBottom, t, backendOnline],
  )

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  // ── D2: stable sandbox callbacks (useCallback → MessageBubble memo holds) ─
  const handleApproveSandbox = useCallback(
    async (token: string, remember = false) => {
      try {
        await approveSandboxApi(token, true, remember)
        useChatStore.getState().approveSandbox()
      } catch {
        // G4: 404 (token expired) or network error → make it visible
        toastBus.error(t('chat.sandboxFailed'))
      }
    },
    [t],
  )
  const handleDenySandbox = useCallback(
    async (token: string) => {
      try {
        await approveSandboxApi(token, false)
        useChatStore.getState().denySandbox()
      } catch {
        // G4: as above
        toastBus.error(t('chat.sandboxFailed'))
      }
    },
    [t],
  )

  // D2: stable tool callbacks for MessageBubble (memo-friendly: the same
  // function references across all renders).
  const approveSandboxForTool = useCallback(
    (tool: ToolCall) => {
      const token = tool.description
      if (token) void handleApproveSandbox(token)
    },
    [handleApproveSandbox],
  )
  const denySandboxForTool = useCallback(
    (tool: ToolCall) => {
      const token = tool.description
      if (token) void handleDenySandbox(token)
    },
    [handleDenySandbox],
  )
  return {
    t,
    isTauri,
    minimize,
    maximize,
    windowVisible,
    currentSession,
    parentLoaded,
    isTyping,
    createSession,
    addMessage,
    setTyping,
    startTurn,
    compactSession,
    checkpoints,
    createCheckpoint,
    rollbackToCheckpoint,
    deleteCheckpoint,
    initFromDb,
    sidebarOpen,
    setSidebarOpen,
    settingsOpen,
    setSettingsOpen,
    railLibraryOpen,
    setRailLibraryOpen,
    settingsTab,
    setSettingsTab,
    sidebarCollapsed,
    setSidebarCollapsed,
    toggleSidebarCollapsed,
    headerMeta,
    setHeaderMeta,
    branchMenuOpen,
    setBranchMenuOpen,
    branchList,
    setBranchList,
    branchBusy,
    setBranchBusy,
    composerSeedNonce,
    composerSeed,
    setComposerSeed,
    fillComposer,
    activeSessionId,
    prevActiveSessionRef,
    refreshHeaderMeta,
    toggleBranchMenu,
    switchBranch,
    navRef,
    suppressNavPushRef,
    navInfo,
    setNavInfo,
    updateNavInfo,
    navigateSession,
    editingTitle,
    setEditingTitle,
    titleDraft,
    setTitleDraft,
    startTitleEdit,
    commitTitleEdit,
    prevUserAt,
    shortcutsOpen,
    setShortcutsOpen,
    backendOnline,
    setBackendOnline,
    engineOnline,
    setEngineOnline,
    wasOnlineRef,
    panelGeo,
    setPanelGeo,
    panelOpen,
    isDesktop,
    panelInset,
    openPaletteFromHeader,
    contextWindow,
    setContextWindow,
    autoCompactDoneRef,
    scheduleJobs,
    setScheduleJobs,
    loadJobs,
    handleScheduleCreate,
    handleScheduleDelete,
    railActive,
    setRailActive,
    messagesEndRef,
    isPinned,
    setIsPinned,
    isPinnedRef,
    abortRef,
    failedTurnRef,
    parentRef,
    rowVirtualizer,
    handleRailSelect,
    handleScroll,
    scrollToBottom,
    pinToBottom,
    wasTypingRef,
    clearActiveSession,
    handleSendRef,
    handleSlashCommand,
    runTurn,
    handleSend,
    handlePickOption,
    handleEditMessage,
    handleRegenerate,
    handleRetry,
    handleStop,
    handleApproveSandbox,
    handleDenySandbox,
    approveSandboxForTool,
    denySandboxForTool,
    handleAnswerAsk,
  }
}
