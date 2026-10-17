import { useTranslation } from 'react-i18next'
import { Bot, ChevronRight, MoreVertical, Pin, Sparkles } from 'lucide-react'
import { formatDistanceToNowStrict } from 'date-fns'
import { Num } from '@/components/ui/Num'
import { Rule } from '@/components/ui/Rule'
import { DEFAULT_SESSION_TITLE } from '@/store/chatStore'
import { dateLocaleFor } from '@/lib/dateLocale'
import { isHelperSessionId } from '@/lib/helperSession'
import { buildSessionTree, filterCollapsedRows, type SessionTreeRow } from '@/lib/sessionTree'

/**
 * The sidebar's task rows, extracted from Sidebar.tsx because the screen is four
 * times over the 400-line wall and this is the block that carries the reading
 * direction.
 *
 * What the direction changed here, and why the row is shaped this way:
 *
 * - A row carries no radius, background, border or hover fill. Two rows are
 *   separated by a Rule between them, and the one line a row may wear on its left
 *   edge is the 2px Rule that says which row is current (`selected`) or running
 *   (`now`).
 * - The trailing meta sits in a `Num`, so the age of every row in the sidebar ends
 *   on one right axis and the digits line up between rows.
 * - Three type steps and no fourth: the row title is the 13px UI step, the meta
 *   line is the 11px data step (mono, tabular, through `Num` and through the
 *   count), and the date group label above the rows is the 11px data step in
 *   caps — the reference renders it as a tlabel, so the 17px title step has no
 *   site in this block.
 * - The accent belongs to what is happening NOW and to nothing else: while a turn
 *   runs, that row's left rule is the 2px brand rule and its message count is the
 *   brand number. Selected is not running, so a selected row marks itself with the
 *   hairline-strong rule and the ink step only. Every other mark in the row (the
 *   helper's Bot, the pin, the unread state) is ink: a state is not an event.
 * - No spinner and no dot: the wait is legible as the record it produces (the
 *   count of what is in the session, in brand, on the row whose work is running).
 */

export interface TaskRowSession {
  id: string
  title: string
  messages: Array<{ id: string; role: string; content: string }>
  createdAt: number
  pinned?: boolean
  unread?: boolean
  parentId?: string
}

/** What the screen owns and the rows read: the one active session, the one
 *  rename draft, the one delete confirmation, and the one open menu. */
export interface TaskRowState {
  activeSessionId: string | null
  /** The session whose turn is running right now — the single row the accent may
   *  mark. Null when nothing runs, which is the normal case. */
  runningSessionId: string | null
  /** Folded branches (a parent's children hidden) — read by the fold toggle. */
  collapsedBranches: Set<string>
  onSelect: (sessionId: string) => void
  onToggleBranch: (sessionId: string) => void
  rename: {
    id: string | null
    draft: string
    setDraft: (value: string) => void
    commit: () => void
    cancel: () => void
  }
  deleteConfirmId: string | null
  onDeleteConfirm: (sessionId: string) => void
  onDeleteCancel: () => void
  onOpenMenu: (sessionId: string, x: number, y: number) => void
  /** The trigger the context menu hands focus back to when it closes. */
  menuReturnRef: React.RefObject<HTMLElement | null>
}

export interface TaskRowGroupProps extends TaskRowState {
  /** `Today`, `Yesterday`, … — the group label from the screen's date grouping. */
  label: string
  sessions: TaskRowSession[]
  collapsed: boolean
  onToggleCollapse: () => void
  collapsedBranches: Set<string>
  /** Icon rail (collapsed sidebar): icons only, no meta line, no rules. */
  rail: boolean
}

const LABEL =
  'flex items-center gap-1.5 w-full py-1.5 pl-1 pr-4 font-mono text-scale-data uppercase tracking-wider text-ink-faint hover:text-ink-soft transition-colors'
const TITLE = 'text-scale-ui'
const DATA = 'font-mono tabular-nums text-scale-data'
const RENAME_INPUT =
  'w-full bg-canvas px-1 py-0.5 text-scale-ui text-ink outline-none border border-hairline-strong'
const MENU_TRIGGER =
  'absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center justify-center min-w-6 min-h-6 text-ink-faint hover:text-ink transition-colors'
const FOLD_TRIGGER =
  'absolute left-0.5 lg:left-0 top-1/2 z-10 -translate-y-1/2 grid place-items-center h-4 w-4 lg:min-h-6 lg:min-w-6 text-ink-faint hover:text-ink-soft'

/** One row: the indent, the title at the UI step, the numbers at the data step,
 *  and the one Rule it may carry on its left edge. */
function TaskRow({
  row,
  rail,
  ...state
}: { row: SessionTreeRow<TaskRowSession>; rail: boolean } & TaskRowState) {
  const { t, i18n } = useTranslation()
  const { session, depth, childCount, rails } = row
  const running = session.id === state.runningSessionId
  const selected = session.id === state.activeSessionId
  // `selected` marks where the reader is, `now` marks what is happening; the
  // running row is both, and the accent outranks the selection line.
  const edge = running ? 'now' : selected ? 'selected' : null
  const renaming = state.rename.id === session.id && !rail
  const title = session.title === DEFAULT_SESSION_TITLE ? t('sidebar.newChat') : session.title

  return (
    <div
      data-session-id={session.id}
      data-testid={`session-row-${session.id}`}
      style={rail ? undefined : { paddingLeft: depth * 12 }}
      className={`group relative ${rail ? 'flex justify-center' : ''}`}
      onContextMenu={(e) => {
        if (rail) return
        e.preventDefault()
        state.onOpenMenu(session.id, e.clientX, e.clientY)
      }}
    >
      {edge && <Rule orientation="vertical" tone={edge} className="absolute inset-y-0 left-0" />}
      {/* P1-9: fold toggle, on parents only; the icon rail carries none. A sibling of the
          select button (no nested button); absolute in the left gutter,
          aria-expanded drives the branch. */}
      {!rail && childCount > 0 && (
        <button
          type="button"
          data-testid={`session-fold-${session.id}`}
          aria-expanded={!state.collapsedBranches.has(session.id)}
          aria-label={
            state.collapsedBranches.has(session.id)
              ? t('sidebar.expandBranch')
              : t('sidebar.collapseBranch')
          }
          onClick={(e) => {
            e.stopPropagation()
            state.onToggleBranch(session.id)
          }}
          className={FOLD_TRIGGER}
        >
          <ChevronRight
            className={`h-3 w-3 transition-transform ${
              state.collapsedBranches.has(session.id) ? '' : 'rotate-90'
            }`}
          />
        </button>
      )}
      <button
        onClick={() => state.onSelect(session.id)}
        title={title}
        className={`w-full text-left transition-colors duration-fast ${
          rail ? 'p-2' : childCount > 0 ? 'pl-6 pr-2.5 py-2' : 'px-2.5 py-2'
        }`}
      >
        {renaming ? (
          <input
            autoFocus
            value={state.rename.draft}
            onChange={(e) => state.rename.setDraft(e.target.value)}
            onBlur={state.rename.commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') state.rename.commit()
              if (e.key === 'Escape') state.rename.cancel()
            }}
            onClick={(e) => e.stopPropagation()}
            className={RENAME_INPUT}
            aria-label={t('sidebar.renameHint')}
          />
        ) : (
          <div className="w-full flex items-center gap-1.5">
            {/* P1-9: ancestor rails (│ as long as the ancestor still has siblings
                below it) + own connector (├ / └). Column depth-1 = own one. The
                step matters: these glyphs used to fall back to the 16px root size
                while the title beside them read 11px. */}
            {!rail &&
              depth > 0 &&
              rails.slice(0, depth - 1).map((cont, k) => (
                <span
                  key={k}
                  aria-hidden="true"
                  className={`w-2 shrink-0 text-center text-ink-faint ${TITLE} font-mono`}
                >
                  {cont ? '│' : ' '}
                </span>
              ))}
            {!rail && depth > 0 && (
              <span
                data-testid={`session-connector-${session.id}`}
                className={`shrink-0 text-ink-faint ${TITLE} font-mono`}
                aria-hidden="true"
              >
                {rails[depth - 1] ? '├' : '└'}
              </span>
            )}
            {/* P1-9: branch badge — the number of direct children. A number, so it
                is set in the data column's figures and wears no pill. */}
            {!rail && childCount > 0 && (
              <span
                data-testid={`session-branch-count-${session.id}`}
                className={`shrink-0 text-ink-faint ${DATA}`}
                aria-hidden="true"
              >
                {childCount}
              </span>
            )}
            {/* A helper chat carries the helper symbol, so between task and
                delegation nobody has to guess from the title. The glyph wears ink: the
                mark names a kind, it does not announce an event. */}
            {isHelperSessionId(session.id) ? (
              <Bot
                data-testid={`session-helper-mark-${session.id}`}
                className="h-3 w-3 shrink-0 text-ink-faint"
                aria-label={t('sidebar.helperChat')}
              />
            ) : (
              <Sparkles className="h-3 w-3 shrink-0 text-ink-faint" />
            )}
            {/* M2: the unread state is typographic now — the title takes an ink
                step — so the marker itself is the word for it, read out rather
                than painted as a 1.5px brand dot on a row that is not running. */}
            {session.unread && !rail && (
              <span
                data-testid={`session-unread-dot-${session.id}`}
                className="sr-only text-scale-data"
              >
                {t('sidebar.filterUnread')}
              </span>
            )}
            {session.pinned && !rail && (
              <Pin
                className="h-3 w-3 shrink-0 text-ink-faint"
                aria-label={t('sidebar.sessionMenu.pinnedAria')}
              />
            )}
            {!rail && (
              <p
                data-testid="session-title-text"
                className={`flex-1 min-w-0 truncate ${TITLE} ${
                  session.unread || selected
                    ? 'text-ink'
                    : 'text-ink-faint group-hover:text-ink-soft'
                }`}
              >
                {title}
              </p>
            )}
          </div>
        )}
        {!rail && (
          <p className="mt-0.5 flex items-baseline justify-between gap-2">
            {/* The record of the session's work. It is the one number on the row
                that moves while a turn runs, so it is the row's "now" — and the
                only number in this block that carries the accent. */}
            <span className={`${DATA} ${running ? 'text-brand-deep' : 'text-ink-faint'}`}>
              {session.messages.length} {t('sidebar.messages')}
            </span>
            <span data-testid={`session-age-${session.id}`}>
              <Num col={1}>
                {formatDistanceToNowStrict(session.createdAt, {
                  locale: dateLocaleFor(i18n?.language),
                  roundingMethod: 'floor',
                })}
              </Num>
            </span>
          </p>
        )}
      </button>

      {/* R26: the ⋯ button (hover/touch) opens the session context menu, and the
          inline confirm below replaces it. Both are the same floating surface as
          before: a transient control over the row is not row chrome. */}
      {!rail && state.deleteConfirmId === session.id ? (
        <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5 float-surface p-0.5 z-sticky">
          <button
            onClick={() => state.onDeleteConfirm(session.id)}
            className="bg-status-danger/20 hover:bg-status-danger/30 text-status-danger rounded px-1.5 py-0.5 lg:min-h-6 text-ui-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 max-lg:min-h-11"
          >
            {t('sidebar.deleteYes')}
          </button>
          <button
            onClick={state.onDeleteCancel}
            className="text-ink-faint hover:text-ink-faint rounded px-1 py-0.5 lg:min-h-6 text-ui-xs transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            {t('sidebar.deleteNo')}
          </button>
        </div>
      ) : (
        !rail && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              state.menuReturnRef.current = e.currentTarget as HTMLElement
              const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
              state.onOpenMenu(session.id, r.left - 150, r.bottom + 4)
            }}
            className={MENU_TRIGGER}
            aria-label={t('sidebar.sessionMenu.aria')}
            data-testid={`session-menu-${session.id}`}
          >
            <MoreVertical className="h-3.5 w-3.5 lg:h-3 lg:w-3" />
          </button>
        )
      )}
    </div>
  )
}

/** One date group: the label at the data step, its rule, and the rows. */
export function TaskRowGroup({
  label,
  sessions,
  collapsed,
  onToggleCollapse,
  rail,
  ...state
}: TaskRowGroupProps) {
  const rows = filterCollapsedRows(buildSessionTree(sessions), state.collapsedBranches)

  return (
    <div>
      <button onClick={onToggleCollapse} aria-expanded={!collapsed} className={LABEL}>
        <ChevronRight
          className={`h-3 w-3 shrink-0 transition-transform ${collapsed ? '' : 'rotate-90'}`}
        />
        {!rail && label}
        {rail && <span className="sr-only">{label}</span>}
        {/* The group's own count ends on the same right edge as every row's age:
            pr-4 above cancels the 6px row indent (ml-1.5) and the row's 10px
            right padding (pr-2.5), so the two columns share one axis. */}
        <Num col={1} className="ml-auto">
          {sessions.length}
        </Num>
      </button>

      {!collapsed && (
        <div data-testid="task-rows" className={`mt-0.5 ${rail ? '' : 'ml-1.5'}`}>
          {rows.map((row, i) => (
            <div key={row.session.id}>
              {/* The rule sits BETWEEN two rows, never on both edges of one, so
                  neighbours can never double a line. */}
              {i > 0 && !rail && <Rule />}
              <TaskRow row={row} rail={rail} {...state} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export { TaskRow }
