/**
 * Ephe — the frame's one column of places (finding #61).
 *
 * Before this, every page drew its own chrome: the chat had a sidebar with the destinations,
 * the other pages had a back arrow to the chat and nothing else. One rail is what makes them
 * one app — the column does not move when the page changes, and a place is reachable from
 * every place.
 *
 * The rail is chrome, so it is solid ink with one hairline: glass is reserved for the surfaces
 * that float above content. A wide window always has it; a phone gets the tab bar instead.
 */
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { IS_DESKTOP_SHELL } from '@/lib/desktopBaseUrl'
import { EpheMark } from './EpheMark'
import { activeDestination, SHELL_DESTINATIONS } from './shellNav'
import type { ShellDestination } from './shellNav'

const ROW =
  'flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-base ease-settle focus-ring'
const IDLE = 'text-ink-faint hover:bg-surface-interactive hover:text-foreground/80'
const ACTIVE = 'bg-brand/15 text-brand-deep'

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

export default function NavRail() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
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
        {places.map((dest) => (
          <RailRow key={dest.id} dest={dest} isActive={active?.id === dest.id} />
        ))}
      </ul>
      <ul role="list" className="mt-auto flex flex-col items-center gap-1 pb-3">
        {footer.map((dest) => (
          <RailRow key={dest.id} dest={dest} isActive={active?.id === dest.id} />
        ))}
      </ul>
    </nav>
  )
}
