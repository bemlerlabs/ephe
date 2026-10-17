import {
  lazy,
  Suspense,
  useState,
  useRef,
  useEffect,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import {
  Menu,
  Sparkles,
  Download,
  Minus,
  Square,
  ArrowDown,
  PanelLeft,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  Library,
  PanelRight,
  Plus,
  HelpCircle,
  Command,
  Sun,
  Moon,
} from 'lucide-react'
import WelcomeEmptyState from '../WelcomeEmptyState'
import ChatSkeleton from './ChatSkeleton'
import { useChatStore, DEFAULT_SESSION_TITLE } from '@/store/chatStore'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { useUpdateCheck } from '@/lib/useUpdateCheck'
import Sidebar from '../Sidebar'
import WorkspaceBar from '../WorkspaceBar'
import ToolbarRow from '../ToolbarRow'
import { UpdateDialog } from '../UpdateDialog'
import ChatInput from '../ChatInput'
import { CellLifeLine } from '../CellLifeLine'
import { estimateContextUsage } from '@/lib/contextMeter'
import MessageBubble from '../MessageBubble'
import SettingsPanel from '../SettingsPanel'
import StatusBar from '../StatusBar'
import TimelineRail from '../TimelineRail'
import { useStatusPanelData } from '../AgentStatusSections'
import AgenticBar, { runStateOf } from '@/components/shell/AgenticBar'
import RunRail from '@/components/shell/RunRail'
import CheckpointControls from '../CheckpointControls'
import SchedulerPanel, { SchedulerMobilePill } from '../SchedulerPanel'
import ForestBackground from '../ForestBackground'
import { useArtifactNotice } from './useArtifactNotice'
import ShortcutOverlay, { SHORTCUTS_EVENT } from '../ShortcutOverlay'
import { getStoredTheme, toggleTheme, type ThemeMode } from '@/lib/theme'
import ErrorBoundary from '@/components/ui/ErrorBoundary'
import { useChatLayoutModel } from './model'
import { useTaskDeepLink } from './useTaskDeepLink'

// W3-1: the two heavy panes are their own chunks. The agent panel drags in xterm
// and every tab; the artifact rail is only needed once a turn produced a file.
// Both load after the chat shell paints instead of riding in the ChatPage chunk.
const ArtifactRail = lazy(() => import('../ArtifactRail'))
const AgentPanel = lazy(() => import('../AgentPanel'))

/**
 * The virtual row key. A row restored from the server mirror arrives without an `id`
 * (lib/restore.ts stamps one on the way in) and keyed as `undefined`, so React warned
 * "Each child in a list should have a unique \"key\" prop" on the first paint of every
 * restored chat. The id is the key when it is there; the row index is the total
 * fallback, so no future projection can bring that warning back to this list.
 */
export function messageRowKey(msg: { id?: string }, index: number): string {
  return msg.id ? msg.id : `row-${index}`
}

/**
 * Chat layout (PWA-Chat-UX-Plan, Phase C1/C2).
 *
 * C1 — SSE rewiring: no WebSocket anymore. Answers arrive via
 *      POST /api/chat/stream (streamChat) → applyStreamEvent → store actions
 *      (exactly 1 growing assistant bubble per turn). Tool approval runs
 *      via POST /api/sandbox/approve (token-based, no auto-approve).
 * C2 — Sessions: initFromDb() loads the persisted sessions from IndexedDB on
 *      mount (active highlight + a11y live in the Sidebar).
 */

export default function ChatLayout() {
  const update = useUpdateCheck()
  useTaskDeepLink()
  const [theme, setTheme] = useState<ThemeMode>(() => getStoredTheme())
  // P1-10: while initFromDb() is running the message list shows a skeleton
  // instead of the welcome state (no empty flash on a cold start).
  const hydrated = useChatStore((s) => s.hydrated)
  const {
    t,
    isTauri,
    minimize,
    maximize,
    currentSession,
    parentLoaded,
    isTyping,
    createSession,
    compactSession,
    checkpoints,
    createCheckpoint,
    rollbackToCheckpoint,
    deleteCheckpoint,
    sidebarOpen,
    setSidebarOpen,
    settingsOpen,
    setSettingsOpen,
    railLibraryOpen,
    setRailLibraryOpen,
    settingsTab,
    setSettingsTab,
    sidebarCollapsed,
    toggleSidebarCollapsed,
    headerMeta,
    branchMenuOpen,
    setBranchMenuOpen,
    branchList,
    branchBusy,
    composerSeed,
    fillComposer,
    toggleBranchMenu,
    switchBranch,
    navInfo,
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
    engineOnline,
    panelGeo,
    panelOpen,
    panelInset,
    openPaletteFromHeader,
    contextWindow,
    scheduleJobs,
    handleScheduleCreate,
    handleScheduleDelete,
    railActive,
    messagesEndRef,
    isPinned,
    parentRef,
    rowVirtualizer,
    handleRailSelect,
    handleScroll,
    pinToBottom,
    handleSlashCommand,
    handleSend,
    handlePickOption,
    handleEditMessage,
    handleRegenerate,
    handleRetry,
    handleStop,
    approveSandboxForTool,
    denySandboxForTool,
    handleAnswerAsk,
  } = useChatLayoutModel()

  // The command/state bar and the run rail read the same status surface the agent
  // popover reads — the live turn, the plan and the goal of the newest turn — so the
  // workbench states one run instead of a second opinion about it.
  const runData = useStatusPanelData(currentSession?.messages ?? [])
  const runState = runStateOf({
    typing: isTyping,
    engineOnline,
    askWaiting: runData.activeTurn?.ask?.status === 'waiting',
    plan: runData.plan,
  })

  // A file that lands while another window has the focus is announced by a toast
  // with a way in. The pane itself stays put (docs/AGENT_PANEL_CONDUCT_2026-10-11.md).
  useArtifactNotice(currentSession)

  // ── W3-57 a11y: the header branch dropdown is a real menu ────────────────
  // Before this it was a naked list of buttons: no role/aria, no arrow roving
  // and no way back out with the keyboard. Same contract as the panel + menu
  // (agent/panelAddMenu.tsx): role=menu / role=menuitem with roving focus,
  // Escape closes ONLY the menu and hands the focus back to the trigger.
  const branchTriggerRef = useRef<HTMLButtonElement>(null)
  const branchMenuRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!branchMenuOpen) return
    // Focus of its own inside the menu, otherwise the arrow keys move the
    // header behind it. The branch list arrives async — focus when it renders.
    const first = branchMenuRef.current?.querySelector<HTMLElement>(
      '[role="menuitem"]:not(:disabled)',
    )
    first?.focus()
  }, [branchMenuOpen, branchList])
  const closeBranchMenu = () => {
    setBranchMenuOpen(false)
    branchTriggerRef.current?.focus()
  }
  const onBranchMenuKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(
      branchMenuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ??
        [],
    )
    const current = items.indexOf(document.activeElement as HTMLElement)
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        if (items.length) items[(current + 1 + items.length) % items.length]?.focus()
        return
      case 'ArrowUp':
        e.preventDefault()
        if (items.length) items[(current - 1 + items.length) % items.length]?.focus()
        return
      case 'Home':
        e.preventDefault()
        items[0]?.focus()
        return
      case 'End':
        e.preventDefault()
        items[items.length - 1]?.focus()
        return
      case 'Tab':
        // Menu convention: Tab closes the menu and lets the browser move on
        // from the trigger — it does not trap focus in a header dropdown.
        setBranchMenuOpen(false)
        return
      case 'Escape':
        e.preventDefault()
        e.stopPropagation()
        closeBranchMenu()
        return
    }
  }

  /* The column only gives up as much width as is left when it itself
     keeps at least 24rem: with a 720 panel and a 1280 window that left
     243 px of chat — the composer had no room to fall back to. */
  const panelInsetCss =
    panelInset > 0 ? `min(${panelInset}px, max(0px, calc(100% - 24rem)))` : undefined

  return (
    <ErrorBoundary>
      <div className="h-screen flex bg-transparent">
        <ForestBackground />
        {/* Sidebar */}
        <Sidebar
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onOpenSettings={(tab) => {
            // Mobile visual check R16: the settings panel (z-overlay) sits BELOW the
            // drawer (z-modal) — when both opened, settings was invisible.
            // Close the drawer so the panel is unobstructed (desktop untouched).
            // P6 B7: optional target tab (sidebar 'plugins' → marketplace).
            setSidebarOpen(false)
            setSettingsTab(tab ?? 'model')
            setSettingsOpen(true)
          }}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={toggleSidebarCollapsed}
        />

        {/* Main chat area — <main> with the skip-link target id (P4-F1):
          "Zum Inhalt springen" (#main-content) had no target. // language-gate: ignore — the German skip-link label the UI renders (locales/de.json:844) */}
        <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 overflow-hidden relative">
          {/* Judge page-5 finding 2026-09-07 (reference-B split parity): with the panel
          open, the content column frees its width on the dock side —
          the send button, model chips and suggestion cards stay reachable.
          On mobile the panel stays an overlay (reference behaviour), Esc/X closes. */}
          <div
            className="flex h-full flex-col relative transition-[padding] duration-base"
            style={
              panelInsetCss
                ? panelGeo.dock === 'right'
                  ? { paddingRight: panelInsetCss }
                  : { paddingLeft: panelInsetCss }
                : undefined
            }
          >
            {/* Header.
              Installed on a phone the web view runs under a black-translucent
              status bar (app/index.html: viewport-fit=cover), so the header has
              to clear the clock itself — `pt-` carries the inset, which is 0 in
              every desktop browser. */}
            <header className="relative z-sticky border-b border-hairline px-4 min-h-12 flex flex-wrap items-center justify-between gap-x-2 gap-y-1 pt-[calc(0.25rem+env(safe-area-inset-top))] pb-1 flex-shrink-0">
              {/* DD-27: the left group is the interactive column (nav arrows, title).
              R2-I: the row has a wrap line (flex-wrap) and the title
              truncates at the column, not at the window (min-w-0 chain instead of a
              vw cap) — with the pane open the chat column is narrower than the
              viewport, and the right-hand island must not reach into its graphics. */}
              <div className="flex items-center gap-1.5 min-w-0 shrink">
                {/* KI-client parity: sidebar toggle in the topbar (desktop) */}
                <button
                  onClick={toggleSidebarCollapsed}
                  aria-label={sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')}
                  aria-pressed={!sidebarCollapsed}
                  data-testid="header-sidebar-toggle"
                  className="hidden md:inline-flex p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors min-h-9 min-w-9"
                >
                  <PanelLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setSidebarOpen(true)}
                  aria-label={t('a11y.menuToggle')}
                  data-testid="header-menu-toggle"
                  className="md:hidden p-2.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors max-lg:min-h-11 max-lg:min-w-11"
                >
                  <Menu className="h-5 w-5 text-brand/60" />
                </button>
                {/* Round 12: ←/→ session navigation (KI-client tab parity) */}
                <div className="hidden md:flex items-center gap-0.5">
                  <button
                    onClick={() => navigateSession(-1)}
                    disabled={!navInfo.canBack}
                    aria-label={t('a11y.navBack')}
                    data-testid="session-nav-back"
                    className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors disabled:opacity-25 disabled:hover:bg-transparent min-h-9 min-w-9"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => navigateSession(1)}
                    disabled={!navInfo.canFwd}
                    aria-label={t('a11y.navForward')}
                    data-testid="session-nav-forward"
                    className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors disabled:opacity-25 disabled:hover:bg-transparent min-h-9 min-w-9"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => createSession()}
                  aria-label={t('sidebar.newChat')}
                  title={t('sidebar.newChat')}
                  data-testid="header-new-session"
                  className="hidden md:inline-flex p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors min-h-9 min-w-9"
                >
                  <Plus className="h-4 w-4" />
                </button>
                <div data-tauri-drag-region className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 shrink-0 rounded-md glass-control flex items-center justify-center">
                    <Sparkles className="h-3 w-3 text-brand" />
                  </div>
                  {/* WP5: under the title sits the life of the cell — not the
                      progress of an animation, but its elapsed time. */}
                  <div className="flex flex-col min-w-0 leading-tight">
                    {editingTitle ? (
                      <input
                        autoFocus
                        value={titleDraft}
                        onChange={(e) => setTitleDraft(e.target.value)}
                        onBlur={commitTitleEdit}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitTitleEdit()
                          if (e.key === 'Escape') setEditingTitle(false)
                        }}
                        aria-label={t('a11y.sessionTitleInput')}
                        data-testid="session-title-input"
                        className="bg-canvas border border-brand/30 rounded-md px-2 py-0.5 text-ui-sm font-semibold text-foreground/90 outline-none w-56"
                      />
                    ) : (
                      <h1
                        data-tauri-drag-region
                        onDoubleClick={startTitleEdit}
                        title={t('a11y.sessionTitleHint')}
                        data-testid="session-title"
                        className="text-ui-sm font-semibold text-foreground/90 select-none truncate min-w-0 max-w-80 cursor-text"
                      >
                        {currentSession?.title === DEFAULT_SESSION_TITLE
                          ? t('sidebar.newChat')
                          : currentSession?.title || t('nav.appName')}
                      </h1>
                    )}
                    <CellLifeLine sessionId={currentSession?.id ?? ''} />
                  </div>
                  {currentSession?.parentId && parentLoaded && (
                    // Z37: fork indicator — the chip leads to the origin session.
                    // Gate on parentLoaded: a parent half outside the
                    // 50-session restore window would be a click that does nothing.
                    <button
                      type="button"
                      data-testid="header-branch-from"
                      onClick={() =>
                        useChatStore.getState().setActiveSession(currentSession!.parentId!)
                      }
                      title={`${t('chat.branchFrom')} #${currentSession.messages.length}`}
                      className="inline-flex items-center gap-1 rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ui-xs text-ink-soft hover:text-foreground hover:border-brand/30 transition-colors max-w-40 min-h-9 max-lg:min-h-11"
                    >
                      <GitBranch className="h-3 w-3 shrink-0 opacity-60" aria-hidden="true" />
                      <span>{t('chat.branchFrom')}</span>
                      <span className="font-mono text-ink-faint">
                        #{currentSession.messages.length}
                      </span>
                    </button>
                  )}
                </div>
                {headerMeta && (
                  <div className="hidden md:flex items-center gap-1.5 min-w-0">
                    {headerMeta.git && headerMeta.branch && (
                      <span className="relative">
                        <button
                          ref={branchTriggerRef}
                          onClick={toggleBranchMenu}
                          aria-label={t('header.branchChip')}
                          aria-haspopup="menu"
                          aria-expanded={branchMenuOpen}
                          aria-controls="branch-menu"
                          data-testid="header-branch-chip"
                          className="inline-flex items-center gap-1 rounded-md glass-control px-2 py-1 text-ui-sm text-ink-soft hover:text-foreground transition-colors max-w-[9rem]"
                        >
                          <GitBranch className="h-3 w-3 shrink-0 text-brand/50" />
                          <span className="truncate">{headerMeta.branch}</span>
                          {headerMeta.dirty > 0 && (
                            <span className="text-status-warning/70">·{headerMeta.dirty}</span>
                          )}
                        </button>
                        {branchMenuOpen && (
                          <div
                            id="branch-menu"
                            ref={branchMenuRef}
                            role="menu"
                            aria-label={t('header.branches')}
                            onKeyDown={onBranchMenuKeyDown}
                            data-testid="branch-menu"
                            className="absolute right-0 top-8 z-modal min-w-44 max-w-64 float-surface py-1.5"
                          >
                            <p className="px-3 py-1 text-ui-xs uppercase tracking-wide text-ink-faint">
                              {t('header.branches')}
                            </p>
                            {branchList.length === 0 && (
                              <p className="px-3 py-1.5 text-ui-xs text-ink-faint">
                                {t('header.noBranches')}
                              </p>
                            )}
                            {branchList.map((b) => (
                              <button
                                key={b}
                                type="button"
                                role="menuitem"
                                tabIndex={-1}
                                onClick={() => switchBranch(b)}
                                disabled={branchBusy}
                                className={`w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-1.5 transition-colors disabled:opacity-40 ${
                                  b === headerMeta.branch
                                    ? 'text-brand bg-brand/10'
                                    : 'text-ink-faint hover:text-foreground hover:bg-surface'
                                }`}
                              >
                                <GitBranch className="h-3 w-3 shrink-0 opacity-60" />
                                <span className="truncate">{b}</span>
                                {b === headerMeta.branch && (
                                  <span className="ml-auto text-ui-xs">✓</span>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </span>
                    )}
                  </div>
                )}
              </div>
              {/* DD-27: at the xl boundary this group measured ~904px against a
              960px main column — it used to overlap the nav buttons and the
              title (pointer events landed on the gauge spans). It is now the
              shrinkable side with an internal scroll strip, same pattern as
              the ToolbarRow tool group. */}
              <div className="hidden md:flex items-center gap-2 min-w-0 shrink">
                {/* R2-U: the update button is always there — checking is an
                    action, not an event you wait for. The dot shows that
                    something is waiting; the dialog states the actual condition,
                    including the one where the check did not get through.
                    U-1: an available update carries the signal itself, a 3.2 s
                    halo and glyph glow (.update-signal), so the user sees that
                    something is here without having to ask. */}
                <button
                  type="button"
                  onClick={() => update.setOpen(true)}
                  aria-label={t('update.open')}
                  title={
                    update.state.phase === 'available' ? t('update.available') : t('update.open')
                  }
                  data-testid="header-update"
                  data-signal={update.show ? 'available' : undefined}
                  className={`relative p-1.5 rounded-lg hover:bg-surface text-ink-faint hover:text-foreground transition-colors duration-base ease-settle min-h-9 min-w-9 max-lg:min-h-11 max-lg:min-w-11${update.show ? ' update-signal' : ''}`}
                >
                  <Download className="h-4 w-4" aria-hidden="true" />
                  {update.show && (
                    <span
                      data-testid="header-update-badge"
                      className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-brand"
                      aria-hidden="true"
                    />
                  )}
                </button>
                <UpdateDialog
                  state={update.state}
                  open={update.open}
                  onOpenChange={update.setOpen}
                  onCheck={() => void update.check()}
                  onInstall={() => void update.install()}
                  onRelaunch={() => void update.relaunch()}
                  releasesUrl={update.state.url}
                  restartBlocked={update.restartBlocked}
                />
                <button
                  type="button"
                  onClick={() => setTheme(toggleTheme())}
                  aria-label={theme === 'light' ? t('theme.toggleDark') : t('theme.toggleLight')}
                  title={theme === 'light' ? t('theme.toggleDark') : t('theme.toggleLight')}
                  data-testid="header-theme"
                  className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors min-h-9 min-w-9 max-lg:min-h-11 max-lg:min-w-11"
                >
                  {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
                </button>
                <button
                  type="button"
                  onClick={() => window.dispatchEvent(new CustomEvent(SHORTCUTS_EVENT))}
                  aria-label={t('shortcuts.title')}
                  title={t('shortcuts.title')}
                  data-testid="header-help"
                  className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors min-h-9 min-w-9 max-lg:min-h-11 max-lg:min-w-11"
                >
                  <HelpCircle className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={openPaletteFromHeader}
                  aria-label={t('chat.openPalette')}
                  title={t('chat.openPalette')}
                  data-testid="header-palette"
                  className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors min-h-9 min-w-9 max-lg:min-h-11 max-lg:min-w-11"
                >
                  <Command className="h-4 w-4" />
                </button>
              </div>
              {/* R38-Judge: the toggles as their own shrink-0 island — they stay fixed at the
                edge; connection/gauges/status pill now live in the status row. */}
              <div className="flex items-center gap-2 shrink-0 ml-auto">
                {/* Toggle inventory 2026-09-07 (reference-B parity): exactly ONE side-panel
                toggle in the header — like the reference product (toggleSidePane).
                Tabs are chosen inside the panel's own tab bar, via ⌘1–5 or the palette;
                the old 5-button cluster duplicated the tab bar a second time. */}
                <button
                  type="button"
                  onClick={() =>
                    window.dispatchEvent(
                      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { toggle: true } }),
                    )
                  }
                  aria-pressed={panelOpen}
                  aria-label={t('chat.sidePanelToggle')}
                  title={t('chat.sidePanelToggle')}
                  data-testid="side-panel-toggle"
                  className={`hidden md:inline-flex p-2 rounded-lg transition-colors items-center min-h-9 min-w-9 ${panelOpen ? 'bg-brand/20 text-brand' : 'text-ink-faint hover:text-foreground/80 hover:bg-surface-interactive'}`}
                >
                  <PanelRight className="h-4 w-4" aria-hidden="true" />
                </button>
                <button
                  onClick={() => setRailLibraryOpen((v) => !v)}
                  aria-label={t('artifacts.library')}
                  aria-pressed={railLibraryOpen}
                  data-testid="artifact-library-toggle"
                  className="hidden md:inline-flex p-2 rounded-lg hover:bg-surface text-ink-faint hover:text-foreground/60 transition-colors"
                >
                  <Library className="h-4 w-4" />
                </button>
                {/* Custom Title Bar — Window Controls (Tauri only) */}
                {isTauri && (
                  <div className="flex items-center gap-1 ml-1 pl-2 border-l border-hairline">
                    <button
                      onClick={minimize}
                      aria-label={t('nav.minimize')}
                      className="p-1.5 rounded-md text-ink-faint hover:text-foreground/70 hover:bg-surface transition-colors"
                    >
                      <Minus className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={maximize}
                      aria-label={t('nav.maximize')}
                      className="p-1.5 rounded-md text-ink-faint hover:text-foreground/70 hover:bg-surface transition-colors"
                    >
                      <Square className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>
            </header>

            {/* The agentic workbench: one chrome line states the run (state, goal,
                plan progress, commands) before the tools and the transcript. */}
            <AgenticBar
              state={runState}
              plan={runData.plan}
              goal={runData.goal}
              onOpenPalette={openPaletteFromHeader}
            />

            {/* R26/R39: toolbar row — five tab buttons + ⌘K palette (meta → header island).
                P1 [F4]: messages supply the chips' "recent artifacts" menu entries. */}
            <ToolbarRow messages={currentSession?.messages ?? []} />

            {/* E-UX: the status row moved BELOW the composer (minimal footer in the
            terminal-harness style); the context ring sits right at the send button. */}

            {/* Checkpoints & Rollback (P2-7) */}
            {currentSession && (
              <div className="px-4 pt-1 flex items-center justify-end">
                <CheckpointControls
                  checkpoints={checkpoints[currentSession.id] ?? []}
                  onCreate={() =>
                    createCheckpoint(
                      t('settings.checkpoint', {
                        n: (checkpoints[currentSession.id]?.length ?? 0) + 1,
                      }),
                    )
                  }
                  onRollback={(id: string) => rollbackToCheckpoint(id)}
                  onDelete={(id: string) => deleteCheckpoint(id)}
                />
              </div>
            )}

            {/* Scheduler (P2-8) — F-24: show the banner only when jobs exist.
            Desktop: the full SchedulerPanel (md:block). Mobile: the ~32px banner
            pushed the welcome area below the fold (deploy-check P1-2),
            hence the compact pill (R40) — DD-10 parity: both surfaces
            show the same information (job count + next run); the pill
            opens the cron surface in the settings. */}
            {scheduleJobs.length > 0 && (
              <>
                <div className="hidden md:block px-4 pt-1">
                  <SchedulerPanel
                    jobs={scheduleJobs}
                    onCreate={(task: string, cron: string) => handleScheduleCreate(task, cron)}
                    onDelete={(id: string) => handleScheduleDelete(id)}
                  />
                </div>
                <div className="md:hidden px-4 pt-1">
                  <SchedulerMobilePill
                    jobs={scheduleJobs}
                    onOpen={() => {
                      setSettingsTab('cron')
                      setSettingsOpen(true)
                    }}
                  />
                </div>
              </>
            )}

            {/* Messages — virtualized (only render visible items) */}
            {!hydrated ? (
              <ChatSkeleton />
            ) : !currentSession || currentSession.messages.length === 0 ? (
              <WelcomeEmptyState onFillComposer={fillComposer} />
            ) : (
              <>
                <div data-testid="chat-scroll-region" className="flex flex-1 min-h-0 relative">
                  {/* G1.4: floating scroll-to-bottom (only when not pinned) */}
                  {!isPinned && (
                    <button
                      onClick={pinToBottom}
                      aria-label={t('chat.scrollToBottom')}
                      className="absolute bottom-4 right-6 z-sticky rounded-full float-surface p-2.5 text-foreground/60 hover:text-brand transition-colors"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </button>
                  )}
                  <TimelineRail
                    messages={currentSession?.messages ?? []}
                    activeIndex={railActive}
                    onSelect={handleRailSelect}
                  />
                  {/* px-4 lives on the SCROLL container: absolutely positioned
                  virtual rows resolve w-full against the inner div's PADDING
                  box — padding on the inner div made rows 32px too wide and
                  clipped the user avatar at the right viewport edge
                  (deploy-check P3, mobile_reply.png). */}
                  <div
                    ref={parentRef}
                    onScroll={handleScroll}
                    data-testid="panel-chat"
                    className="flex-1 overflow-y-auto px-4"
                    style={{ overflowAnchor: 'auto' }}
                  >
                    <div
                      className="max-w-5xl mx-auto py-6 relative"
                      style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
                    >
                      {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                        const msg = currentSession?.messages[virtualItem.index]
                        if (!msg) return null
                        return (
                          <div
                            key={messageRowKey(msg, virtualItem.index)}
                            ref={rowVirtualizer.measureElement}
                            data-index={virtualItem.index}
                            data-testid="message-row"
                            className="absolute left-0 w-full"
                            style={{
                              transform: `translateY(${virtualItem.start}px)`,
                              paddingBottom: 16,
                            }}
                          >
                            <MessageBubble
                              sessionId={currentSession?.id}
                              animateEntrance={
                                virtualItem.index >= (currentSession?.messages.length ?? 0) - 3
                              }
                              // D2: direct msg reference (no {...msg} spread) —
                              // updateActiveMessage creates a new object per chunk only for
                              // the ACTIVE message; historical bubbles keep
                              // their reference → memo skips them.
                              message={msg}
                              onApproveSandbox={approveSandboxForTool}
                              onDenySandbox={denySandboxForTool}
                              onEdit={handleEditMessage}
                              onRegenerate={handleRegenerate}
                              onRetry={handleRetry}
                              onPickOption={handlePickOption}
                              onAnswerAsk={handleAnswerAsk}
                              prevUserContent={prevUserAt[virtualItem.index] ?? ''}
                            />
                          </div>
                        )
                      })}
                    </div>
                    {/* Mobile buffer: on narrow screens the composer grows into
                    two rows — without the buffer the last message ran
                    past its edge (computer-use finding t23, 2026-10-01). */}
                    <div aria-hidden="true" className="h-16 lg:h-0" />
                  </div>
                  <RunRail plan={runData.plan} />
                </div>
                <div ref={messagesEndRef} />
              </>
            )}

            {/* Input — G1.3: NOT disabled while streaming (typing/queueing stay
            possible); only the send button turns into stop. Backstop guard in the
            parent's handleSend. */}
            <WorkspaceBar
              branch={headerMeta?.branch}
              dirty={headerMeta?.dirty}
              git={headerMeta?.git}
            />
            <ChatInput
              onSend={(msg, att) => void handleSend(msg, att)}
              streaming={isTyping}
              onStop={handleStop}
              onSlashCommand={handleSlashCommand}
              draftSeed={composerSeed}
              contextPercent={
                (currentSession?.messages.length ?? 0) > 0
                  ? Math.min(
                      100,
                      (estimateContextUsage(currentSession?.messages ?? [], contextWindow).tokens
                        .total /
                        Math.max(1, contextWindow ?? 32768)) *
                        100,
                    )
                  : null
              }
            />
            {/* Minimal footer (E-UX): agent status + live tok/s + context meter.
            CPU/RAM/Disk + uptime live in the expandable agent status. */}
            <StatusBar
              messages={currentSession?.messages ?? []}
              windowTokens={contextWindow}
              onCompact={compactSession}
              sessionId={currentSession?.id}
              backendOnline={backendOnline}
              engineOnline={engineOnline}
              typing={isTyping}
            />
          </div>
        </main>
        {/* P2-1: artifact preview rail (right side, only when artifacts exist) */}
        <Suspense fallback={null}>
          <ArtifactRail
            messages={currentSession?.messages ?? []}
            sessionId={currentSession?.id}
            libraryOpen={railLibraryOpen}
            onCloseLibrary={() => setRailLibraryOpen(false)}
          />
        </Suspense>
        {/* Round 14: shortcut cheatsheet ('?') */}
        <ShortcutOverlay open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
        {/* G2/G1: agent panel (tabs: live preview | terminal), opens via Cmd-K */}
        <Suspense fallback={null}>
          <AgentPanel messages={currentSession?.messages ?? []} />
        </Suspense>
        {/* Settings Panel */}
        <SettingsPanel
          isOpen={settingsOpen}
          initialTab={settingsTab === 'model' ? 'engine' : settingsTab}
          onClose={() => setSettingsOpen(false)}
        />
      </div>
    </ErrorBoundary>
  )
}
