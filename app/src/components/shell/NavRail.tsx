/**
 * Ephe — the frame's one column of places (finding #61), and since register #107 the
 * one column of the whole left edge.
 *
 * Before this, every page drew its own chrome: the chat had a sidebar with the destinations,
 * the other pages had a back arrow to the chat and nothing else. One rail is what makes them
 * one app — the column does not move when the page changes, and a place is reachable from
 * every place.
 *
 * The second column the chat carried was a second sidebar: it stood beside this rail at
 * 56 px, repeated the two frame verbs (New task, Search) and named places the rows below
 * already name. It is the body of the Task row now, so the left edge is one column of
 * icons that says what the app has, and the task list opens out of it when asked for and
 * folds back when it is not.
 *
 * The rail is chrome, so it is solid ink with one hairline: glass is reserved for the surfaces
 * that float above content. A wide window always has it; a phone gets the tab bar instead.
 */
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Plus, Search } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { IS_DESKTOP_SHELL } from '@/lib/desktopBaseUrl'
import { openCommandPalette } from '@/lib/commandPalette'
import { setRegisterOpen, toggleRegister, useRegisterOpen } from '@/lib/taskRegister'
import { EpheMark } from './EpheMark'
import { activeDestination, SHELL_DESTINATIONS } from './shellNav'
import type { ShellDestination } from './shellNav'

const ROW =
  'flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-base ease-settle focus-ring'
const IDLE = 'text-ink-faint hover:bg-surface-interactive hover:text-foreground/80'
const ACTIVE = 'bg-brand/15 text-brand-deep'

/** The two frame verbs the task column used to carry. A phone has no rail, so its drawer
 *  keeps both rows; on a wide window they live here and nowhere else. */
const RAIL_ACTIONS = [
  { id: 'new-task', testid: 'new-session', labelKey: 'sidebar.newChat', Icon: Plus },
  { id: 'search', testid: 'nav-rail-search', labelKey: 'sidebar.actionSearch', Icon: Search },
] as const

function RailRow({ dest, isActive }: { dest: ShellDestination; isActive: boolean }) {
  const { t } = useTranslation()
  const label = t(dest.labelKey)
  const Icon = dest.Icon
  return (
    <li>
      <Link
        to={dest.path}
        title={label}
        aria-label={label}
        aria-current={isActive ? 'page' : undefined}
        data-testid={`nav-rail-${dest.id}`}
        data-active={isActive || undefined}
        className={`${ROW} ${isActive ? ACTIVE : IDLE} max-lg:hidden`}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </Link>
    </li>
  )
}

/** Task is a destination and a door: from another place it goes to the chat and shows the
 *  register, on the chat it opens and closes what the row holds — one gesture per meaning. */
function RegisterRow({ dest, isActive }: { dest: ShellDestination; isActive: boolean }) {
  const { t } = useTranslation()
  const open = useRegisterOpen()
  const label = t(dest.labelKey)
  const Icon = dest.Icon
  return (
    <li>
      <button
        type="button"
        onClick={() => (isActive ? toggleRegister() : setRegisterOpen(true))}
        title={label}
        aria-label={label}
        aria-current={isActive ? 'page' : undefined}
        aria-expanded={open}
        aria-controls={isActive ? 'chat-sidebar' : undefined}
        data-testid={`nav-rail-${dest.id}`}
        data-active={isActive || undefined}
        data-open={open || undefined}
        className={`${ROW} ${isActive ? ACTIVE : IDLE} max-lg:hidden`}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </button>
    </li>
  )
}

export default function NavRail() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const createSession = useChatStore((store) => store.createSession)
  const active = activeDestination(pathname)
  // Settings is the one place that is not a destination in the moment, so it sits apart.
  const places = SHELL_DESTINATIONS.filter((one) => one.id !== 'settings')
  const footer = SHELL_DESTINATIONS.filter((one) => one.id === 'settings')

  return (
    <nav
      aria-label={t('shell.navAria')}
      data-testid="nav-rail"
      className="z-overlay flex w-14 shrink-0 flex-col items-center border-r border-hairline bg-canvas max-lg:hidden"
    >
      {/* The macOS window draws its traffic lights over the top-left corner of this column,
          exactly as the chat sidebar's header clears them. */}
      <div
        data-tauri-drag-region
        className={`flex w-full justify-center pb-2 ${IS_DESKTOP_SHELL ? 'pt-9' : 'pt-3'}`}
      >
        <EpheMark size="1.25rem" testId="rail-mark" />
      </div>
      <ul role="list" className="flex flex-col items-center gap-1">
        {RAIL_ACTIONS.map((action) => {
          const Icon = action.Icon
          return (
            <li key={action.id}>
              <button
                type="button"
                onClick={() => {
                  if (action.id === 'new-task') {
                    createSession()
                    navigate('/')
                  } else {
                    openCommandPalette()
                  }
                }}
                title={t(action.labelKey)}
                aria-label={t(action.labelKey)}
                data-testid={action.testid}
                className={`${ROW} ${IDLE}`}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
              </button>
            </li>
          )
        })}
        {/* The verbs above start things; the rows below are places. One hairline says so. */}
        <li aria-hidden="true" className="my-1.5 h-px w-6 bg-hairline" />
        {places.map((dest) =>
          dest.id === 'task' ? (
            <RegisterRow key={dest.id} dest={dest} isActive={active?.id === dest.id} />
          ) : (
            <RailRow key={dest.id} dest={dest} isActive={active?.id === dest.id} />
          ),
        )}
      </ul>
      <ul role="list" className="mt-auto flex flex-col items-center gap-1 pb-3">
        {footer.map((dest) => (
          <RailRow key={dest.id} dest={dest} isActive={active?.id === dest.id} />
        ))}
      </ul>
    </nav>
  )
}
