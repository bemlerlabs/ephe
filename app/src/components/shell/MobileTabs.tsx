/**
 * Ephe — the phone's answer to the rail (finding #61).
 *
 * One name for both (`shell.navAria`), because they are one navigation drawn for two viewports:
 * a device shows exactly one of them.
 *
 * A thumb does not reach a left edge, so the same five places the rail names travel along the
 * bottom instead. One list feeds both (`shellNav.ts`), which is the reason a place cannot
 * appear in one column and quietly go missing from the other.
 */
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { TAB_BAR_DESTINATIONS, activeDestination } from './shellNav'

const ROW =
  'flex min-h-11 flex-1 flex-col items-center justify-center gap-0.5 rounded-lg text-ui-2xs transition-colors duration-base ease-settle focus-ring'

export default function MobileTabs() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const active = activeDestination(pathname)

  return (
    <nav
      aria-label={t('shell.navAria')}
      data-testid="mobile-tabs"
      className="z-sticky flex shrink-0 items-stretch border-t border-hairline bg-canvas pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {TAB_BAR_DESTINATIONS.map((dest) => {
        const isActive = active?.id === dest.id
        const label = t(dest.labelKey)
        const Icon = dest.Icon
        return (
          <Link
            key={dest.id}
            to={dest.path}
            aria-current={isActive ? 'page' : undefined}
            data-testid={`mobile-tab-${dest.id}`}
            data-active={isActive || undefined}
            className={`${ROW} ${isActive ? 'text-brand-deep' : 'text-ink-faint hover:text-foreground/80'}`}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            <span className="truncate px-1">{label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
