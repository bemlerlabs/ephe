'use client'

import {
  useEffect,
  useRef,
  useState,
  Fragment,
  type KeyboardEvent as ReactKeyboardEvent,
  type ComponentType,
} from 'react'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import {
  Sparkles,
  Plus,
  X,
  Trash2,
  Settings,
  Search,
  ChevronRight,
  ChevronLeft,
  Pencil,
  FolderClosed,
  Clock,
  AlertTriangle,
  MoreVertical,
  Pin,
  PinOff,
  Copy,
  CalendarClock,
  Blocks,
  Circle,
  CheckCircle2,
  LayoutGrid,
  Folder,
  FileDown,
  Archive,
  Activity,
  Flag,
  FolderOpen,
  GitBranch,
  Store,
  Users,
  ListTodo,
  Brain,
  Plug,
  Library,
  Wrench,
} from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { openExternally } from '@/lib/nativeBrowser'
import type { TabKey } from '@/components/dashboard/settings/types'
import { SESSION_MENU_GROUPS, type SessionMenuEntryId } from './sessionMenuEntries'
import {
  OPEN_TIERS_KEY,
  SIDEBAR_ACTION_TIERS,
  readOpenTiers,
  type SidebarActionEntryId,
  type SidebarCollapsibleTierId,
} from './sidebarActionGroups'
import { format, isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns'
import type { Locale } from 'date-fns'
import { dateLocaleFor } from '@/lib/dateLocale'
import {
  listProjects,
  listSchedules,
  updateSettings,
  getTasks,
  getSettings,
  exportChatMarkdown,
  downloadTextFile,
  searchSessions,
  type ProjectSummary,
  type ScheduleJob,
  type TaskItem,
  type SessionSearchHit,
} from '@/lib/api'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { WORKSPACE_CHANGED_EVENT } from './WorkspacePicker'
import { TaskRowGroup } from './SidebarTaskRows'
import { toastBus } from '@/lib/toast'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
  /** P6 B7: optional target tab (e.g. 'plugins' for the marketplace). */
  onOpenSettings: (tab?: TabKey | 'model') => void
  /** Desktop collapse (KI-client style): collapsible down to the icon rail. */
  collapsed: boolean
  onToggleCollapsed: () => void
}

// Date group type
interface DateGroup {
  label: string
  sessions: Session[]
}

// Session type matching the store
interface Session {
  id: string
  title: string
  messages: Array<{ id: string; role: string; content: string }>
  createdAt: number
  pinned?: boolean
  archived?: boolean
  unread?: boolean
  parentId?: string
}

// Simple date groupings
function groupSessionsByDate(
  sessions: Session[],
  t: (key: string) => string,
  dateLocale: Locale,
): DateGroup[] {
  const groups: DateGroup[] = []

  const groupLabel = (date: Date): string => {
    if (isToday(date)) return t('sidebar.today')
    if (isYesterday(date)) return t('sidebar.yesterday')
    if (isThisWeek(date, { weekStartsOn: 1 })) return t('sidebar.thisWeek')
    if (isThisMonth(date)) return t('sidebar.thisMonth')
    return format(date, 'MMMM yyyy', { locale: dateLocale })
  }

  // Pinned first, then newest (deploy-check P2-2: groupSessionsByDate used to
  // discard the pinned-first order by re-sorting on createdAt alone).
  const sorted = [...sessions].sort(
    (a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.createdAt - a.createdAt,
  )

  let currentLabel = ''
  let currentSessions: Session[] = []

  for (const session of sorted) {
    const label = groupLabel(new Date(session.createdAt))
    if (label !== currentLabel) {
      if (currentSessions.length > 0) {
        groups.push({ label: currentLabel, sessions: currentSessions })
      }
      currentLabel = label
      currentSessions = [session]
    } else {
      currentSessions.push(session)
    }
  }
  if (currentSessions.length > 0) {
    groups.push({ label: currentLabel, sessions: currentSessions })
  }

  return groups
}

export default function Sidebar({
  isOpen,
  onClose,
  onOpenSettings,
  collapsed,
  onToggleCollapsed,
}: SidebarProps) {
  const { t, i18n } = useTranslation()
  const {
    sessions,
    activeSessionId,
    isTyping,
    setActiveSession,
    createSession,
    deleteSession,
    renameSession,
    togglePin,
    toggleArchive,
    markUnread,
    branchSession,
  } = useChatStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [searchFocused, setSearchFocused] = useState(false)
  // K3 Z35 (reference parity): on top of the title filter, content hits
  // from the FTS5 index (GET /api/search) — debounced, honest emptiness accepted.
  const [contentHits, setContentHits] = useState<SessionSearchHit[]>([])
  useEffect(() => {
    const q = searchQuery.trim()
    if (!q) {
      setContentHits([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      searchSessions(q, 6)
        .then((r) => {
          if (!cancelled) setContentHits(r.results ?? [])
        })
        .catch(() => {
          if (!cancelled) setContentHits([])
        })
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [searchQuery])
  // Collapsible data groups (Ponytail: the header buttons were dead → now a toggle)
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const toggleGroup = (label: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }
  // P1-9: collapsed revision branches (per branch, not per group).
  const [collapsedBranches, setCollapsedBranches] = useState<Set<string>>(new Set())
  const toggleBranch = (id: string) => {
    setCollapsedBranches((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  // Phase F: inline rename (pencil hover button → input, Enter/blur confirms)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  // R26: PROJECTS tree — workspace projects + automations (mockup section).
  // Projects: a click sets the active workspace folder (persisted).
  // Automations: scheduler jobs with a clock icon (ok) or a warning icon (disabled/no run).
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [schedules, setSchedules] = useState<ScheduleJob[]>([])
  // Round-G3 (reference parity): view Group|Project + tasks section.
  const [viewMode, setViewMode] = useState<'group' | 'project'>(
    () => (localStorage.getItem('ephe.sidebar.view') as 'group' | 'project') || 'group',
  )
  const [tasks, setTasks] = useState<TaskItem[]>([])
  useEffect(() => {
    let cancelled = false
    getTasks()
      .then((r) => {
        if (!cancelled) setTasks((r ?? []).filter((x) => x.status !== 'done').slice(0, 4))
      })
      .catch(() => {
        /* offline → section hidden */
      })
    return () => {
      cancelled = true
    }
  }, [])
  const switchView = (mode: 'group' | 'project') => {
    setViewMode(mode)
    localStorage.setItem('ephe.sidebar.view', mode)
  }
  // #71: the two lower nav tiers are disclosures, closed on first run and
  // remembered per person. Closed first, because "unclear what is primary" was
  // the finding — the headless primary tier is what a first visit sees. The head
  // keeps the member count, so nothing looks lost, and one click brings a tier
  // back for good (the value is a per-person preference and outlives the session).
  const [openTiers, setOpenTiers] = useState<Record<SidebarCollapsibleTierId, boolean>>(() =>
    readOpenTiers(localStorage.getItem(OPEN_TIERS_KEY)),
  )
  const toggleTier = (id: SidebarCollapsibleTierId) => {
    setOpenTiers((prev) => {
      const next = { ...prev, [id]: !prev[id] }
      localStorage.setItem(OPEN_TIERS_KEY, JSON.stringify(next))
      return next
    })
  }
  // P2-3 (reference parity, image): ≡ filter popover. The axes are the real
  // session flags (pinned/unread/archived) + the sort axis; persisted per key.
  const [filterOpen, setFilterOpen] = useState(false)
  const [pinnedOnly, setPinnedOnly] = useState(
    () => localStorage.getItem('ephe.sidebar.f.pinned') === '1',
  )
  const [unreadOnly, setUnreadOnly] = useState(
    () => localStorage.getItem('ephe.sidebar.f.unread') === '1',
  )
  const [showArchived, setShowArchived] = useState(
    () => localStorage.getItem('ephe.sidebar.f.archived') === '1',
  )
  const [ordering, setOrdering] = useState<'updated' | 'created'>(
    () => (localStorage.getItem('ephe.sidebar.f.order') as 'updated' | 'created') || 'updated',
  )
  const toggleFilter = (key: 'pinned' | 'unread' | 'archived', val: boolean) => {
    const map = { pinned: setPinnedOnly, unread: setUnreadOnly, archived: setShowArchived } as const
    map[key](val)
    localStorage.setItem(`ephe.sidebar.f.${key}`, val ? '1' : '0')
  }
  const applyOrdering = (mode: 'updated' | 'created') => {
    setOrdering(mode)
    localStorage.setItem('ephe.sidebar.f.order', mode)
  }
  const resetFilters = () => {
    toggleFilter('pinned', false)
    toggleFilter('unread', false)
    toggleFilter('archived', false)
    applyOrdering('updated')
  }
  // K1 (reference parity): sidebar width persisted in px (like the panel),
  // separator with drag + double-click-to-fit. 200..480px, fit default 288 (w-72).
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const raw = Number(localStorage.getItem('ephe.sidebar.width'))
    return raw >= 200 && raw <= 480 ? raw : 288
  })
  const sidebarWidthRef = useRef(sidebarWidth)
  sidebarWidthRef.current = sidebarWidth
  const onSidebarResizeDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = sidebarWidthRef.current
    const onMove = (ev: PointerEvent) => {
      const next = startWidth + (ev.clientX - startX)
      sidebarWidthRef.current = Math.min(Math.max(next, 200), 480)
      setSidebarWidth(sidebarWidthRef.current)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      localStorage.setItem('ephe.sidebar.width', String(sidebarWidthRef.current))
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }
  const fitSidebar = () => {
    setSidebarWidth(288)
    sidebarWidthRef.current = 288
    localStorage.setItem('ephe.sidebar.width', '288')
  }
  const openPanelTab = (tab: string) => {
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
  }
  const openPalette = () => {
    // ⌘K parity: use the same toggle as the hook handler (isPaletteToggle).
    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'k', metaKey: true, ctrlKey: false, bubbles: true }),
    )
  }
  useEffect(() => {
    let cancelled = false
    listProjects()
      .then((r) => {
        if (!cancelled) setProjects(r.projects ?? [])
      })
      .catch(() => {
        /* offline → section hidden */
      })
    listSchedules()
      .then((r) => {
        if (!cancelled) setSchedules((r.jobs ?? []).slice(0, 4))
      })
      .catch(() => {
        /* offline → section hidden */
      })
    return () => {
      cancelled = true
    }
  }, [])
  const handleProjectPick = async (project: ProjectSummary) => {
    try {
      await updateSettings({ workspace_dir: project.path })
      window.dispatchEvent(
        new CustomEvent(WORKSPACE_CHANGED_EVENT, { detail: { path: project.path } }),
      )
    } catch {
      // F-6: a failed switch must not stay silent — the label keeps the old
      // workspace, the toast explains why nothing moved.
      toastBus.error(t('common.changeFailed'))
    }
  }

  // R26: Session context menu (right-click on the row, or the ⋯ hover button —
  // same menu as leading AI clients): Pin/Unpin, Rename, Copy session ID, Delete.
  const [menu, setMenu] = useState<{ sessionId: string; x: number; y: number } | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  // W3-57 a11y: the element that opened the menu — Escape hands the focus back.
  const menuReturnRef = useRef<HTMLElement | null>(null)
  const openMenu = (sessionId: string, x: number, y: number) => {
    // Real menu height ~520px (16 entries at 24px + 4 separators at 9px +
    // 12px padding). The clamping buffer has to be this real height, otherwise
    // the lower part (export/delete) falls below the
    // edge on a small viewport. Math.max(8,..) keeps a positive top when innerHeight <
    // menu height (then the container scrolls thanks to max-h/overflow-y, see below).
    const MENU_H = 520
    setMenu({
      sessionId,
      x: Math.min(x, window.innerWidth - 190),
      y: Math.max(8, Math.min(y, window.innerHeight - MENU_H)),
    })
  }
  useEffect(() => {
    if (!menu) return
    const close = () => setMenu(null)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null)
    }
    window.addEventListener('click', close)
    window.addEventListener('resize', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('resize', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu])
  // W3-57 a11y: the session menu is a real menu — focus moves in when it opens,
  // arrows rove over the entries, Escape closes it and returns the focus to the
  // ⋯ trigger (the same contract as the header branch menu in chat/index.tsx).
  useEffect(() => {
    if (!menu) return
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
  }, [menu])
  const closeMenuToTrigger = () => {
    setMenu(null)
    menuReturnRef.current?.focus()
  }
  const onSessionMenuKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
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
        setMenu(null)
        return
      case 'Escape':
        e.preventDefault()
        e.stopPropagation()
        closeMenuToTrigger()
        return
    }
  }
  const menuSession = menu ? sessions.find((s) => s.id === menu.sessionId) : null
  const copySessionId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id)
      toastBus.success(t('sidebar.sessionMenu.copied'))
    } catch {
      toastBus.error(t('sidebar.sessionMenu.copyFailed'))
    }
  }
  // M2 (reference parity): paths for the copy entries — workspace,
  // tasks file, audit log (path constants as in the backend, core/tasks.py).
  const [wsDir, setWsDir] = useState('')
  useEffect(() => {
    getSettings()
      .then((s) => setWsDir(s.workspace_dir ?? ''))
      .catch(() => {})
  }, [])
  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      toastBus.success(t('sidebar.sessionMenu.copied'))
    } catch {
      toastBus.error(t('sidebar.sessionMenu.copyFailed'))
    }
  }
  // Desktop (lg+ ≥1024px) → permanent column; below that → slide drawer.
  const isDesktop = useMediaQuery('(min-width: 1024px)')
  // Rail mode only on desktop; the mobile drawer always renders expanded
  // (otherwise the X close disappears when collapsed is persisted in the localStorage)
  const rail = isDesktop && collapsed

  // DD-25: null-message placeholders (automatically created fresh sessions)
  // are not conversations — they skewed the list as a "New Session,
  // 0 messages" phantom. Hidden, except the currently active one (otherwise the
  // current entry is missing after New Session).
  const filteredSessions = sessions
    .filter((s) => (showArchived ? true : !s.archived))
    .filter((s) => s.messages.length > 0 || s.id === activeSessionId)
    .filter((s) => !pinnedOnly || s.pinned)
    .filter((s) => !unreadOnly || s.unread)
    .filter((s) => !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    .sort((a, b) => (ordering === 'created' ? b.createdAt - a.createdAt : 0))
    .sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.createdAt - a.createdAt)

  const dateGroups = groupSessionsByDate(filteredSessions, t, dateLocaleFor(i18n?.language))

  const handleDelete = (id: string) => {
    deleteSession(id)
    setDeleteConfirm(null)
  }

  // Phase F: inline rename
  const startRename = (id: string, title: string) => {
    setRenamingId(id)
    setRenameDraft(title)
  }
  const commitRename = () => {
    if (renamingId) renameSession(renamingId, renameDraft)
    setRenamingId(null)
    setRenameDraft('')
  }

  // M2/W10: the session context menu's rows. The ORDER and the SET come from the
  // ONE list (SESSION_MENU_GROUPS in sessionMenuEntries.ts) — the test reads its
  // expectation from the same list, so the menu and its test cannot drift apart.
  // Everything that is not order — icon, label key, action, the danger tone — is
  // gathered here, next to the handlers it closes over.
  const sessionMenuRows: Record<
    SessionMenuEntryId,
    {
      icon: ComponentType<{ className?: string }>
      labelKey: string
      onSelect: () => void
      danger?: boolean
    }
  > | null =
    menu && menuSession
      ? {
          pin: {
            icon: menuSession.pinned ? PinOff : Pin,
            labelKey: menuSession.pinned ? 'sidebar.sessionMenu.unpin' : 'sidebar.sessionMenu.pin',
            onSelect: () => togglePin(menu.sessionId),
          },
          rename: {
            icon: Pencil,
            labelKey: 'sidebar.sessionMenu.rename',
            onSelect: () => startRename(menu.sessionId, menuSession.title),
          },
          archive: {
            icon: Archive,
            labelKey: 'sidebar.sessionMenu.archive',
            onSelect: () => toggleArchive(menu.sessionId),
          },
          unread: {
            icon: Circle,
            labelKey: 'sidebar.sessionMenu.markUnread',
            onSelect: () => markUnread(menu.sessionId),
          },
          'show-path': {
            icon: FolderOpen,
            labelKey: 'sidebar.sessionMenu.showProjectPath',
            onSelect: () => {
              if (wsDir) void toastBus.info(wsDir)
            },
          },
          'copy-path': {
            icon: Copy,
            labelKey: 'sidebar.sessionMenu.copyPath',
            onSelect: () => void copyText(wsDir),
          },
          'copy-task-path': {
            icon: Copy,
            labelKey: 'sidebar.sessionMenu.copyTaskPath',
            onSelect: () => void copyText('~/.ephe/tasks.json'),
          },
          'copy-log-path': {
            icon: Copy,
            labelKey: 'sidebar.sessionMenu.copyLogPath',
            onSelect: () => void copyText('~/.ephe/audit.log'),
          },
          'copy-id': {
            icon: Copy,
            labelKey: 'sidebar.sessionMenu.copyId',
            onSelect: () => void copySessionId(menu.sessionId),
          },
          'goto-config': {
            icon: Settings,
            labelKey: 'sidebar.sessionMenu.gotoConfig',
            onSelect: () => onOpenSettings(),
          },
          trajectory: {
            icon: Activity,
            labelKey: 'sidebar.sessionMenu.trajectory',
            onSelect: () => openPanelTab('trajectory'),
          },
          // Z37: session fork from the last entry of the listed session
          branch: {
            icon: GitBranch,
            labelKey: 'sidebar.sessionMenu.branch',
            onSelect: () => {
              const src = sessions.find((x) => x.id === menu.sessionId)
              const lastId = src?.messages[src.messages.length - 1]?.id
              if (lastId) {
                setActiveSession(menu.sessionId)
                branchSession(lastId)
              }
            },
          },
          'report-issue': {
            icon: Flag,
            labelKey: 'sidebar.sessionMenu.reportIssue',
            onSelect: () => {
              // Inside the shell `window.open` has no way out of the web view
              // (measured 2026-10-12: the link did nothing in the desktop
              // build). `openExternally` hands the URL to the OS there, and
              // falls back to `window.open` with noopener in the PWA.
              void openExternally('https://github.com/bemlerlabs/ephe/issues')
            },
          },
          // K2 (Z38 parity): markdown export via the orphan route /api/export
          export: {
            icon: FileDown,
            labelKey: 'sidebar.sessionMenu.export',
            onSelect: () => {
              void exportChatMarkdown(
                (menuSession.messages ?? []).map((mm) => ({
                  role: String(mm.role ?? ''),
                  content: String(mm.content ?? ''),
                })),
              )
                .then((md) => {
                  downloadTextFile(`ephe-${menu.sessionId}.md`, md)
                  toastBus.success(t('sidebar.sessionMenu.exported'))
                })
                .catch(() => toastBus.error(t('sidebar.sessionMenu.exportFailed')))
            },
          },
          delete: {
            icon: Trash2,
            labelKey: 'sidebar.sessionMenu.delete',
            onSelect: () => setDeleteConfirm(menu.sessionId),
            danger: true,
          },
        }
      : null

  // #71: the sidebar's destination rows, keyed by entry id. The ORDER and the
  // TIERS come from the ONE list (SIDEBAR_ACTION_TIERS in sidebarActionGroups.ts,
  // read by Sidebar.g3.test.tsx too); everything that is not order — icon, label,
  // hint, target — is gathered here, next to the handlers it closes over, the
  // same shape the session menu above uses. The testids are the ones the rows
  // carried while they stood flat: the grouping adds a level above them.
  const sideNavRows: Record<
    SidebarActionEntryId,
    {
      testid: string
      Icon: ComponentType<{ className?: string }>
      label: string
      hint: string
      run: () => void
    }
  > = {
    skills: {
      testid: 'sidebar-action-skills',
      Icon: Blocks,
      label: t('sidebar.navCapabilities'),
      hint: '',
      run: () => onOpenSettings('skills'),
    },
    tools: {
      testid: 'sidebar-action-tools',
      Icon: Wrench,
      label: t('sidebar.navTools'),
      hint: '',
      run: () => {
        window.location.hash = '#/tools'
      },
    },
    helpers: {
      // Swarm/subagent runs — named honestly instead of "Messaging".
      testid: 'sidebar-action-helpers',
      Icon: Users,
      label: t('sidebar.navHelpers'),
      hint: '',
      run: () => openPanelTab('subagents'),
    },
    marketplace: {
      // P6 B7 (ref-01): the skill store as its own nav row —
      // jumps straight into the plugins tab of the settings.
      testid: 'sidebar-action-marketplace',
      Icon: Store,
      label: t('sidebar.navMarketplace'),
      hint: '',
      run: () => onOpenSettings('plugins'),
    },
    files: {
      testid: 'sidebar-action-files',
      Icon: FolderOpen,
      label: t('sidebar.navFiles'),
      hint: '',
      run: () => openPanelTab('files'),
    },
    workspaces: {
      // W1: with several agents running in parallel, "which agent is on
      // which file, and do two of them collide" needs one page.
      testid: 'sidebar-action-workspaces',
      Icon: GitBranch,
      label: t('sidebar.navWorkspaces'),
      hint: '',
      run: () => {
        window.location.hash = '#/workspaces'
      },
    },
    knowledge: {
      // R2-A: knowledge ("what remains") is a page with sub-pages. The
      // panel tab stays the quick view from inside the chat.
      testid: 'sidebar-action-knowledge',
      Icon: Brain,
      label: t('sidebar.navKnowledge'),
      hint: '',
      run: () => {
        // HashRouter: the address is the route. No useNavigate here —
        // the surface is also checked outside the router.
        window.location.hash = '#/memory'
      },
    },
    library: {
      // Library pattern: generated end products in one place.
      testid: 'sidebar-action-library',
      Icon: Library,
      label: t('sidebar.navLibrary'),
      hint: '',
      run: () => window.dispatchEvent(new CustomEvent('ephe:library-open')),
    },
    artifacts: {
      // R4-A2: the workbench got a page; the pop-up in the
      // chat stays as the quick view from inside a task.
      testid: 'sidebar-action-artifacts',
      Icon: Archive,
      label: t('sidebar.navArtifacts'),
      hint: '',
      run: () => {
        window.location.hash = '#/artifacts'
      },
    },
    automations: {
      // Cron/automations live in the settings — the name now says where.
      testid: 'sidebar-action-automations',
      Icon: CalendarClock,
      label: t('sidebar.navScheduled'),
      hint: '',
      run: () => onOpenSettings('cron'),
    },
    connectors: {
      testid: 'sidebar-action-connectors',
      Icon: Plug,
      label: t('sidebar.navConnectors'),
      hint: '',
      run: () => onOpenSettings('mcp'),
    },
    search: {
      testid: 'sidebar-action-search',
      Icon: Search,
      label: t('sidebar.actionSearch'),
      hint: '⌘K',
      run: () => openPalette(),
    },
    tasks: {
      testid: 'sidebar-action-tasks',
      Icon: ListTodo,
      label: t('sidebar.navTasks'),
      hint: '',
      run: () => onOpenSettings('tasks'),
    },
  }

  return (
    <>
      {/* Mobile overlay — above the header (z-modal), otherwise the header
          swallows the tap-away clicks */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-canvas/80 backdrop-blur-sm z-modal lg:hidden"
          onClick={onClose}
          data-testid="sidebar-backdrop"
        />
      )}

      {/* Sidebar — desktop (lg+): permanent column without slide animation
          (framer-motion sets an inline transform that overrides the CSS classes —
          with !isOpen it would therefore push the sidebar out of the viewport).
          Mobile: drawer with spring transition + backdrop, z ABOVE the header
          (otherwise the header blocks the X close — regression finding round 10). */}
      <m.aside
        initial={isDesktop ? false : { x: -320 }}
        animate={isDesktop ? { x: 0 } : { x: isOpen ? 0 : -320 }}
        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
        className={`left-0 top-0 h-full glass-float border-r border-brand/10 flex flex-col ${
          isDesktop ? 'relative z-overlay' : 'fixed z-modal'
        } ${rail ? 'w-14' : 'w-72'} transition-[width] duration-base overflow-hidden`}
        style={!rail && isDesktop ? { width: sidebarWidth } : undefined}
        role={isDesktop ? undefined : 'dialog'}
        aria-modal={isDesktop ? undefined : true}
        aria-label={t('a11y.sidebar')}
        data-testid="chat-sidebar"
        data-collapsed={rail || undefined}
      >
        {/* K1: drag separator on the outer edge of the sidebar (desktop only, expanded) */}
        {!rail && isDesktop && (
          <div
            onPointerDown={onSidebarResizeDown}
            onDoubleClick={fitSidebar}
            data-testid="sidebar-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label={t('a11y.sidebar')}
            className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-brand/20 transition-colors z-sticky"
          />
        )}
        {/* Header — rail: its own centred expand button (w-14 does not fit
            logo + button in one row -> the button was clipped).
            On a phone this is the top of the drawer, under the clock: the top
            inset is carried by `pt-` (0 on desktop, where the drawer is a
            normal column). */}
        <div
          className={`border-b border-hairline ${rail ? 'px-2 py-3' : 'px-4 pb-4 pt-[calc(1rem+env(safe-area-inset-top))]'}`}
        >
          {rail ? (
            <div className="flex flex-col items-center gap-2 mb-3">
              <div className="w-7 h-7 rounded-lg glass-control flex items-center justify-center shrink-0">
                <Sparkles className="h-3.5 w-3.5 text-brand" />
              </div>
              {isDesktop && (
                <button
                  onClick={onToggleCollapsed}
                  className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors"
                  aria-label={t('sidebar.expand')}
                  data-testid="sidebar-expand-toggle"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="flex items-center justify-end gap-1">
                {isDesktop && (
                  <button
                    onClick={onToggleCollapsed}
                    className="p-1.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors"
                    aria-label={t('sidebar.collapse')}
                    data-testid="sidebar-collapse-toggle"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                )}
                <button
                  onClick={onClose}
                  aria-label={t('a11y.close')}
                  className="lg:hidden p-2.5 rounded-lg hover:bg-surface text-ink-soft hover:text-foreground transition-colors max-lg:min-w-11 max-lg:min-h-11"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </>
          )}

          {/* New Session — the only "New task" entry point: the extra ⌘N row
              below it was a real duplicate (finding 2026-10-01, t1-audit).
              The shortcut now lives as a hint inside the pill itself. */}
          <button
            onClick={() => {
              createSession()
              // The phone drawer has to end the pick with the pick itself
              // (measured 2026-10-12: the backdrop stayed mounted and the user
              // had to tap away). The desktop column is permanent — there the
              // sidebar stays.
              if (!isDesktop) onClose()
            }}
            data-testid="new-session"
            className="w-full bg-brand/80 hover:bg-brand border border-brand/20 text-black/90 rounded-xl h-9 max-lg:h-11 text-ui-xs font-semibold transition-all duration-base flex items-center justify-center gap-1.5 forest-glow"
            aria-label={t('sidebar.newChat')}
            title={t('sidebar.newChat')}
          >
            <Plus className="h-3.5 w-3.5" />
            {!rail && <span className="flex-1 text-center">{t('sidebar.newChat')}</span>}
            {!rail && <span className="text-black/60 font-mono text-[10px] pr-1">⌘N</span>}
          </button>

          {/* P2-2 → 2026 IA-Sweep : nav in everyday language, every
              entry opens what its name points to — no developer terms
              left on the way. Labels come from i18n, shortcuts only when expanded. */}
          {!rail && (
            // #71: three tiers instead of thirteen equal-looking rows. The
            // primary tier carries no head — the pill above it and the two rows
            // below it are what "primary" means here. The two lower tiers are
            // disclosures: the head keeps the member count, and `hidden` takes
            // the rows out of the flow and the accessibility tree WITHOUT
            // unmounting them, so a collapsed tier keeps whatever state its
            // rows hold and the same testids stay in the document.
            //
            // The height cap is not decoration. Measured 2026-10-14 on the
            // 288x800 column: with both tiers open the island wants 503px, the
            // header takes the room and the task list below it collapsed to 8px
            // while the rows past the fold were simply clipped (the aside is
            // overflow-hidden). Capped and scrollable, the list keeps its room
            // and every row stays reachable.
            <div
              className="px-1 pt-1 space-y-0.5 max-h-[45vh] overflow-y-auto overscroll-contain"
              data-testid="sidebar-actions"
            >
              {SIDEBAR_ACTION_TIERS.map((tier) => {
                const rows = tier.entries.map((id) => ({ id, ...sideNavRows[id] }))
                const renderRow = ({
                  id,
                  testid,
                  Icon,
                  label,
                  hint,
                  run,
                }: (typeof rows)[number]) => (
                  <button
                    key={id}
                    onClick={() => run()}
                    data-testid={testid}
                    data-tier={tier.id}
                    className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors max-lg:min-h-11"
                  >
                    <Icon className="h-3.5 w-3.5 text-ink-faint shrink-0" />
                    <span className="flex-1 text-left truncate">{label}</span>
                    {hint && <span className="text-ui-xs text-ink-faint shrink-0">{hint}</span>}
                  </button>
                )

                if (!tier.collapsible) {
                  return (
                    <div
                      key={tier.id}
                      data-testid={`sidebar-tier-${tier.id}`}
                      data-tier={tier.id}
                      className="space-y-0.5"
                    >
                      {rows.map(renderRow)}
                    </div>
                  )
                }

                const open = openTiers[tier.id as SidebarCollapsibleTierId]
                return (
                  <div
                    key={tier.id}
                    data-testid={`sidebar-tier-${tier.id}`}
                    data-tier={tier.id}
                    className="pt-1.5"
                  >
                    <button
                      type="button"
                      onClick={() => toggleTier(tier.id as SidebarCollapsibleTierId)}
                      data-testid={`sidebar-tier-${tier.id}-toggle`}
                      aria-expanded={open}
                      aria-controls={`sidebar-tier-${tier.id}-rows`}
                      title={tier.labelKey ? t(tier.labelKey) : undefined}
                      className="w-full flex items-start gap-1.5 rounded-lg px-1 py-1.5 text-ui-xs font-medium text-ink-faint tracking-wide hover:text-ink-soft hover:bg-surface-interactive transition-colors max-lg:min-h-11"
                    >
                      <ChevronRight
                        className={`h-3 w-3 mt-0.5 shrink-0 transition-transform ${
                          open ? 'rotate-90' : ''
                        }`}
                      />
                      <span className="flex-1 text-left leading-tight">
                        {tier.labelKey ? t(tier.labelKey) : ''}
                      </span>
                      <span
                        data-testid={`sidebar-tier-${tier.id}-count`}
                        className="text-ui-2xs bg-surface-raised px-1.5 py-0.5 rounded-full shrink-0"
                      >
                        {rows.length}
                      </span>
                    </button>
                    <div
                      id={`sidebar-tier-${tier.id}-rows`}
                      data-testid={`sidebar-tier-${tier.id}-rows`}
                      hidden={!open}
                      className="space-y-0.5 mt-0.5 ml-1.5"
                    >
                      {rows.map(renderRow)}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Round-G3: Group|Project view toggle (reference pattern). */}
          {!rail && (
            <div className="px-3 pt-2 pb-1 flex items-center gap-1.5">
              <div
                className="flex items-center rounded-lg border border-hairline bg-surface p-0.5"
                data-testid="sidebar-view-toggle"
              >
                <button
                  onClick={() => switchView('group')}
                  data-testid={viewMode === 'group' ? 'sidebar-view-group-active' : undefined}
                  aria-pressed={viewMode === 'group'}
                  className={`flex items-center gap-1 px-2 py-1 rounded-md text-ui-xs font-medium transition-colors lg:min-h-6 max-lg:min-h-11 ${viewMode === 'group' ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground'}`}
                >
                  <LayoutGrid className="h-3 w-3" />
                  {t('sidebar.viewGroup')}
                </button>
                <button
                  onClick={() => switchView('project')}
                  data-testid={viewMode === 'project' ? 'sidebar-view-project-active' : undefined}
                  aria-pressed={viewMode === 'project'}
                  className={`flex items-center gap-1 px-2 py-1 rounded-md text-ui-xs font-medium transition-colors lg:min-h-6 max-lg:min-h-11 ${viewMode === 'project' ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground'}`}
                >
                  <Folder className="h-3 w-3" />
                  {t('sidebar.viewProject')}
                </button>
              </div>
              {/* P2-3: ≡ filter popover (reference pattern, image) */}
              <button
                onClick={() => setFilterOpen((v) => !v)}
                aria-expanded={filterOpen}
                aria-label={t('sidebar.filterTitle')}
                data-testid="sidebar-filter-toggle"
                className="flex items-center justify-center p-1.5 lg:min-w-6 lg:min-h-6 rounded-md text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors max-lg:min-w-11 max-lg:min-h-11"
              >
                <MoreVertical className="h-3.5 w-3.5 lg:h-3 lg:w-3" />
              </button>
            </div>
          )}
          {filterOpen && !rail && (
            <div className="px-3 pb-1" data-testid="sidebar-filter-popover">
              <div className="rounded-lg border border-hairline bg-canvas p-2 space-y-1.5">
                <p className="text-ui-xs font-medium text-ink-faint uppercase tracking-wider px-0.5">
                  {t('sidebar.filterTitle')}
                </p>
                {/* Ordering */}
                <div className="flex items-center justify-between gap-2 px-0.5">
                  <span className="text-ui-sm text-ink-soft">{t('sidebar.ordering')}</span>
                  <div className="flex items-center gap-0.5">
                    <button
                      onClick={() => applyOrdering('updated')}
                      aria-pressed={ordering === 'updated'}
                      data-testid="sidebar-filter-order-updated"
                      className={`px-1.5 py-0.5 lg:min-h-6 rounded text-ui-xs max-lg:min-h-11 ${ordering === 'updated' ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground'}`}
                    >
                      {t('sidebar.orderingUpdated')}
                    </button>
                    <button
                      onClick={() => applyOrdering('created')}
                      aria-pressed={ordering === 'created'}
                      data-testid="sidebar-filter-order-created"
                      className={`px-1.5 py-0.5 lg:min-h-6 rounded text-ui-xs max-lg:min-h-11 ${ordering === 'created' ? 'bg-brand/20 text-brand' : 'text-ink-soft hover:text-foreground'}`}
                    >
                      {t('sidebar.orderingCreated')}
                    </button>
                  </div>
                </div>
                {/* Flags */}
                {(
                  [
                    ['pinned', 'sidebar.filterPinned', pinnedOnly],
                    ['unread', 'sidebar.filterUnread', unreadOnly],
                    ['archived', 'sidebar.filterArchived', showArchived],
                  ] as const
                ).map(([key, labelKey, on]) => (
                  <button
                    key={key}
                    onClick={() => toggleFilter(key, !on)}
                    aria-pressed={on}
                    data-testid={`sidebar-filter-${key}`}
                    className="w-full flex items-center justify-between gap-2 px-0.5 py-0.5 lg:min-h-6 rounded text-ui-sm hover:bg-surface-interactive transition-colors max-lg:min-h-11"
                  >
                    <span className="text-ink-soft">{t(labelKey)}</span>
                    <span
                      className={`h-3.5 w-3.5 rounded border flex items-center justify-center ${on ? 'bg-brand/20 border-brand/40 text-brand' : 'border-hairline text-transparent'}`}
                    >
                      ✓
                    </span>
                  </button>
                ))}
                <div className="flex items-center gap-1 pt-0.5">
                  <button
                    onClick={() => setCollapsedGroups(new Set(dateGroups.map((g) => g.label)))}
                    data-testid="sidebar-filter-collapse-all"
                    className="flex-1 px-1.5 py-1 lg:min-h-6 rounded-md text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors max-lg:min-h-11"
                  >
                    {t('sidebar.collapseAll')}
                  </button>
                  <button
                    onClick={resetFilters}
                    data-testid="sidebar-filter-reset"
                    className="flex-1 px-1.5 py-1 lg:min-h-6 rounded-md text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors max-lg:min-h-11"
                  >
                    {t('sidebar.resetDefaults')}
                  </button>
                </div>
                <button
                  onClick={() => sessions.filter((s) => s.unread).forEach((s) => markUnread(s.id))}
                  data-testid="sidebar-filter-mark-read"
                  className="w-full px-1.5 py-1 lg:min-h-6 rounded-md text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors max-lg:min-h-11"
                >
                  {t('sidebar.markAllRead')}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Search (only when expanded) */}
        {!rail && (
          <div className="px-3 py-2.5">
            <div
              className={`relative flex items-center rounded-lg border transition-all duration-base ${
                searchFocused ? 'border-brand/20 bg-surface' : 'border-hairline bg-surface'
              }`}
            >
              <Search className="h-3.5 w-3.5 text-ink-faint absolute left-2.5" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setSearchFocused(false)}
                placeholder={t('sidebar.searchPlaceholder')}
                data-testid="sidebar-search"
                className="w-full bg-transparent pl-8 pr-2.5 lg:pr-8 py-1.5 text-ui-xs text-foreground/70 placeholder:text-ink-faint outline-none max-lg:min-h-11 max-lg:pr-11 max-lg:text-ui-input"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  data-testid="sidebar-search-clear"
                  className="absolute right-2 lg:right-0.5 grid place-items-center lg:min-w-6 lg:min-h-6 text-ink-faint hover:text-ink-soft max-lg:right-0 max-lg:min-w-11 max-lg:min-h-11"
                  aria-label={t('a11y.close')}
                >
                  <X className="h-3 w-3 lg:h-3.5 lg:w-3.5" />
                </button>
              )}
            </div>
          </div>
        )}

        {/* K3 Z35: content hits (FTS5) below the filter field — a click opens the session */}
        {!rail && searchQuery.trim() !== '' && contentHits.length > 0 && (
          <div className="px-3 pb-2 space-y-1" data-testid="sidebar-content-hits">
            {contentHits.map((hit, i) => (
              <button
                key={`${hit.session_id}-${i}`}
                type="button"
                data-testid={`sidebar-content-hit-${i}`}
                onClick={() => setActiveSession(hit.session_id)}
                className="w-full text-left rounded-lg px-2 py-1.5 text-ui-xs text-ink-faint hover:text-foreground hover:bg-surface transition-colors max-lg:min-h-11"
              >
                <span className="block truncate font-medium text-foreground/80">
                  {hit.session_title}
                </span>
                <span className="block truncate text-ui-xs text-ink-faint">
                  {(hit.snippet || hit.content || '').replace(/[‹›]/g, '')}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* R26/G3: PROJECTS tree — in the group view only when projects exist;
            in the project view it is the primary grouping and stays put. */}
        {!rail && viewMode === 'project' && (projects.length > 0 || schedules.length > 0) && (
          <div className="px-3 pb-2" data-testid="sidebar-projects">
            <p className="py-1.5 px-1 text-ui-xs font-medium text-ink-faint uppercase tracking-wider">
              {t('sidebar.projects')}
            </p>
            <div className="space-y-0.5 mt-0.5 ml-1.5">
              {projects.slice(0, 6).map((p) => (
                <button
                  key={p.path}
                  onClick={() => {
                    void handleProjectPick(p)
                  }}
                  title={p.path}
                  data-testid="sidebar-project"
                  aria-current={p.workspace ? 'true' : undefined}
                  className="w-full text-left rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 hover:bg-surface-interactive transition-colors"
                >
                  {/* W2: active workspace project = green pin, like the reference */}
                  {p.workspace && (
                    <span
                      data-testid="sidebar-project-dot"
                      className="h-1 w-1 rounded-full bg-brand shrink-0"
                      aria-hidden="true"
                    />
                  )}
                  <FolderClosed className="h-3 w-3 shrink-0 text-brand/50" aria-hidden="true" />
                  <span className="text-ui-xs text-ink-faint truncate">{p.name}</span>
                </button>
              ))}
              {schedules.map((job) => {
                const warn = job.enabled === false
                return (
                  <div
                    key={job.id}
                    title={job.cron}
                    data-testid="sidebar-automation"
                    className="rounded-lg px-2.5 py-1 flex items-center gap-1.5 text-ink-faint"
                  >
                    {warn ? (
                      <AlertTriangle
                        className="h-3 w-3 shrink-0 text-status-warning/60"
                        aria-hidden="true"
                      />
                    ) : (
                      <Clock className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
                    )}
                    <span className="text-ui-sm truncate">{job.task}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Round-G3: TASKS section (reference) — open to-dos from the
            tasks tab, a click opens that tab in the page pane. */}
        {!rail && tasks.length > 0 && (
          <div className="px-3 pb-2" data-testid="sidebar-tasks">
            <p className="py-1.5 px-1 text-ui-xs font-medium text-ink-faint uppercase tracking-wider">
              {t('sidebar.tasksSection')}
            </p>
            <div className="space-y-0.5 mt-0.5 ml-1.5">
              {tasks.map((task) => (
                <button
                  key={task.id}
                  onClick={() => onOpenSettings('tasks')}
                  data-testid={`sidebar-task-row-${task.id}`}
                  title={task.title}
                  className="w-full text-left rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 hover:bg-surface-interactive transition-colors"
                >
                  {task.status === 'done' ? (
                    <CheckCircle2 className="h-3 w-3 shrink-0 text-brand/60" aria-hidden="true" />
                  ) : (
                    <Circle className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
                  )}
                  <span
                    className={`text-ui-xs truncate ${task.status === 'done' ? 'text-ink-faint line-through' : 'text-ink-faint'}`}
                  >
                    {task.title}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Session List — Date Grouped */}
        <div
          className={`flex-1 overflow-y-auto pb-2 ${rail ? 'px-1.5' : 'px-3'}`}
          data-testid="sessions-view"
        >
          {dateGroups.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-10 h-10 rounded-xl glass-control flex items-center justify-center mb-3">
                <Sparkles className="h-5 w-5 text-ink-faint" />
              </div>
              {!rail && <p className="text-ui-xs text-ink-faint">{t('sidebar.noSessions')}</p>}
              {/* P1-F2: only ONE empty state (the hero in the chat) — the sidebar stays
                  plain (icon), no second competing CTA. */}
            </div>
          ) : (
            <div className="space-y-4">
              {dateGroups.map((group) => (
                <TaskRowGroup
                  key={group.label}
                  label={group.label}
                  sessions={group.sessions}
                  collapsed={collapsedGroups.has(group.label)}
                  onToggleCollapse={() => toggleGroup(group.label)}
                  rail={rail}
                  activeSessionId={activeSessionId}
                  runningSessionId={isTyping ? activeSessionId : null}
                  collapsedBranches={collapsedBranches}
                  onSelect={(id) => {
                    setActiveSession(id)
                    if (window.innerWidth < 1024) onClose()
                  }}
                  onToggleBranch={toggleBranch}
                  rename={{
                    id: renamingId,
                    draft: renameDraft,
                    setDraft: setRenameDraft,
                    commit: commitRename,
                    cancel: () => {
                      setRenamingId(null)
                      setRenameDraft('')
                    },
                  }}
                  deleteConfirmId={deleteConfirm}
                  onDeleteConfirm={handleDelete}
                  onDeleteCancel={() => setDeleteConfirm(null)}
                  onOpenMenu={openMenu}
                  menuReturnRef={menuReturnRef}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer — "Settings & profile" (R26 mockup): avatar + label + gear.
            Toggle inventory 2026-09-07 (reference-B parity): this footer card is the
            ONLY settings entry in the shell — the header gear and its mobile-QR
            shortcut were retired; the panel itself deep-links the mobile tab. */}
        <div className={`border-t border-hairline ${rail ? 'p-2' : 'p-3'}`}>
          <button
            onClick={() => onOpenSettings()}
            title={t('sidebar.settingsAndProfile')}
            data-testid="sidebar-settings-btn"
            className="w-full glass-control rounded-xl px-2.5 py-2 flex items-center gap-2.5 text-ink-soft hover:text-foreground hover:bg-brand/10 transition-all"
            aria-label={t('sidebar.settingsAndProfile')}
          >
            <span
              className="w-7 h-7 rounded-full bg-brand/20 flex items-center justify-center shrink-0"
              aria-hidden="true"
            >
              <Sparkles className="h-3.5 w-3.5 text-brand" />
            </span>
            {!rail && (
              <>
                <span className="flex-1 min-w-0 text-left">
                  <span className="block text-ui-sm font-medium text-foreground/80 truncate">
                    {t('sidebar.settingsAndProfile')}
                  </span>
                  <span className="block text-ui-xs text-ink-faint">v{__APP_VERSION__}</span>
                </span>
                <Settings className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </>
            )}
            {rail && <Settings className="h-3.5 w-3.5" aria-hidden="true" />}
          </button>
        </div>
      </m.aside>

      {/* R26: Session context menu — fixed, cursor/button-anchored, OUTSIDE the
          aside (the mobile drawer has a transform → fixed children would anchor
          to it instead of the viewport). */}
      {menu && menuSession && (
        <div
          data-testid="session-context-menu"
          ref={menuRef}
          role="menu"
          aria-label={t('sidebar.sessionMenu.aria')}
          onKeyDown={onSessionMenuKeyDown}
          className="fixed z-modal min-w-52 max-h-[calc(100vh-16px)] overflow-y-auto float-surface py-1.5"
          style={{ left: menu.x, top: menu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* M2/W10 (reference parity): the rows come from the ONE list
              (SESSION_MENU_GROUPS, sessionMenuEntries.ts) and a rule divides each
              group, so the set and the order cannot drift from the test. */}
          {sessionMenuRows &&
            SESSION_MENU_GROUPS.map((group, gi) => (
              <Fragment key={group[0]}>
                {gi > 0 && (
                  <div
                    data-testid={`menu-sep-${gi}`}
                    className="my-1 border-t border-hairline"
                    aria-hidden="true"
                  />
                )}
                {group.map((id) => {
                  const row = sessionMenuRows[id]
                  const Icon = row.icon
                  return (
                    <button
                      key={id}
                      role="menuitem"
                      tabIndex={-1}
                      data-testid={`menu-${id}`}
                      onClick={() => {
                        row.onSelect()
                        setMenu(null)
                      }}
                      className={
                        row.danger
                          ? 'w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-status-danger/80 hover:text-status-danger hover:bg-status-danger/10 transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2'
                          : 'w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:text-foreground hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2'
                      }
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {t(row.labelKey)}
                    </button>
                  )
                })}
              </Fragment>
            ))}
        </div>
      )}
    </>
  )
}
