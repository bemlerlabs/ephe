'use client'

/**
 * The task dock: the toolbar's content, shown when a chat is under way.
 *
 * The permanent toolbar row made the shell read as a cockpit before a word was
 * typed. This dock appears only after a session has messages and there is more
 * than one task, a plan with steps, or a connected git project; the welcome
 * stays clean. It lives at the bottom-right of the chat column — the side with
 * the room — floats over the transcript, and can be collapsed or dismissed for
 * the session. Below 1024px it starts as a pill: an open 19rem dock would cover
 * most of a phone transcript.
 */
import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, FolderClosed, GitBranch, MonitorPlay, TerminalSquare, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useChatStore, DEFAULT_SESSION_TITLE } from '@/store/chatStore'
import { EpheMark } from '@/components/shell/EpheMark'
import type { ChatMessage, PlanCardSpec } from '@/types'

const DESTINATIONS = [
  { tab: 'files', labelKey: 'toolbar.files', Icon: FolderClosed },
  { tab: 'preview', labelKey: 'toolbar.preview', Icon: MonitorPlay },
  { tab: 'terminal', labelKey: 'toolbar.develop', Icon: TerminalSquare },
  { tab: 'git', labelKey: 'toolbar.gitConsole', Icon: GitBranch },
] as const

interface TaskDockProps {
  messages: ChatMessage[]
  plan?: PlanCardSpec | null
  headerMeta?: { git?: boolean; branch?: string } | null
}

export function TaskDock({ messages, plan, headerMeta }: TaskDockProps) {
  const { t } = useTranslation()
  const sessions = useChatStore((s) => s.sessions)
  const currentSession = useChatStore((s) => s.currentSession)
  const activeSessionId = useChatStore((s) => s.activeSessionId)
  const setActiveSession = useChatStore((s) => s.setActiveSession)
  const wide = useMediaQuery('(min-width: 1024px)')
  // null follows the viewport default; a click pins the choice for the session,
  // so switching tasks does not reopen the dock on a narrow column.
  const [collapsed, setCollapsed] = useState<boolean | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const isCollapsed = collapsed ?? !wide

  const sessionId = currentSession?.id ?? ''
  useEffect(() => {
    setDismissed(false)
  }, [sessionId])

  const tasks = useMemo(
    () => sessions.filter((session) => !session.deletedAt && !session.archived).slice(0, 5),
    [sessions],
  )
  const steps = plan?.items ?? []
  const git = Boolean(headerMeta?.git && headerMeta.branch)
  const started = messages.length > 0
  const show = started && !dismissed && (tasks.length > 1 || git || steps.length > 1)
  if (!show) return null

  const openTab = (tab: string) =>
    window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))

  if (isCollapsed) {
    return (
      <button
        type="button"
        data-testid="task-dock-pill"
        onClick={() => setCollapsed(false)}
        aria-label={t('taskDock.expand')}
        aria-expanded={false}
        className="absolute bottom-16 end-3 z-sticky inline-flex items-center gap-2 glass-control rounded-full px-3 py-1.5 text-ui-xs text-ink-soft pointer-coarse:min-h-11 transition-colors hover:text-foreground motion-safe:animate-in motion-safe:fade-in-0"
      >
        <EpheMark size="1.1rem" />
        {t('taskDock.title')}
        <span className="font-mono tabular-nums text-ink-faint">{tasks.length}</span>
      </button>
    )
  }

  return (
    <aside
      data-testid="task-dock"
      aria-label={t('taskDock.title')}
      className="absolute bottom-16 end-3 z-sticky w-[19rem] max-w-[calc(100%-1.5rem)] float-surface motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-2"
    >
      <header className="flex items-center gap-2 border-b border-hairline px-3 py-2">
        <EpheMark size="1.2rem" />
        <span className="text-ui-xs font-medium text-foreground/90">{t('taskDock.title')}</span>
        <span className="font-mono text-ui-xs tabular-nums text-ink-faint">{tasks.length}</span>
        <span className="ml-auto flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            aria-label={t('taskDock.collapse')}
            aria-expanded
            data-testid="task-dock-collapse"
            className="rounded p-1 text-ink-faint transition-colors hover:text-foreground pointer-coarse:min-h-11 pointer-coarse:min-w-11"
          >
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label={t('taskDock.dismiss')}
            data-testid="task-dock-dismiss"
            className="rounded p-1 text-ink-faint transition-colors hover:text-foreground pointer-coarse:min-h-11 pointer-coarse:min-w-11"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </span>
      </header>

      <div className="max-h-[18rem] overflow-y-auto p-2">
        <ul aria-label={t('taskDock.title')}>
          {tasks.map((task) => {
            const active = task.id === activeSessionId
            return (
              <li key={task.id}>
                <button
                  type="button"
                  onClick={() => setActiveSession(task.id)}
                  aria-current={active ? 'true' : undefined}
                  data-testid={`task-dock-row-${task.id}`}
                  className={`pointer-coarse:min-h-11 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-ui-xs transition-colors ${
                    active
                      ? 'bg-brand/10 text-foreground'
                      : 'text-ink-soft hover:bg-surface-interactive hover:text-foreground'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${active ? 'bg-brand' : 'bg-hairline-strong'}`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1 truncate">
                    {task.title === DEFAULT_SESSION_TITLE ? t('sidebar.newChat') : task.title}
                  </span>
                  <span className="shrink-0 font-mono tabular-nums text-ui-xs text-ink-faint">
                    {task.messages.length}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>

        {steps.length > 0 && (
          <section className="mt-2 border-t border-hairline pt-2" aria-label={t('taskDock.steps')}>
            <p className="px-2 pb-1 text-ui-xs uppercase tracking-wider text-ink-faint">
              {t('taskDock.steps')}
            </p>
            <ul>
              {steps.slice(0, 4).map((step, index) => (
                <li
                  key={`${index}:${step.text}`}
                  className="flex items-center gap-2 px-2 py-0.5 text-ui-xs text-ink-soft"
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      step.status === 'done'
                        ? 'bg-status-success'
                        : step.status === 'active'
                          ? 'bg-brand'
                          : step.status === 'failed'
                            ? 'bg-status-danger'
                            : 'bg-hairline-strong'
                    }`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 truncate">{step.text}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {git && (
          <div className="mt-2 border-t border-hairline px-2 pt-2">
            <span
              className="inline-flex max-w-full items-center gap-1 rounded-md glass-control px-1.5 py-0.5 text-ui-xs text-ink-soft"
              title={t('header.branchChip')}
            >
              <GitBranch className="h-3 w-3 shrink-0 text-brand/60" aria-hidden="true" />
              <span className="truncate">{headerMeta?.branch}</span>
            </span>
          </div>
        )}

        <div
          role="group"
          aria-label={t('toolbar.group')}
          className="mt-2 flex items-center gap-1 border-t border-hairline pt-2"
        >
          {DESTINATIONS.map(({ tab, labelKey, Icon }) => (
            <button
              key={tab}
              type="button"
              onClick={() => openTab(tab)}
              title={t(labelKey)}
              aria-label={t(labelKey)}
              data-testid={`task-dock-tool-${tab}`}
              className="inline-flex min-h-8 items-center gap-1 rounded-md px-1.5 text-ui-xs pointer-coarse:min-h-11 text-ink-faint transition-colors hover:bg-surface-interactive hover:text-foreground"
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden xl:inline">{t(labelKey)}</span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  )
}
