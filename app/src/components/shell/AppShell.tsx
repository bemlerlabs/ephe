/**
 * Ephe — one frame around every page (finding #61).
 *
 * The recommendation was concrete: a permanent rail, one window, and a tab bar on a phone.
 * What it replaced was a set of pages that each drew their own chrome — the chat carried the
 * destinations in its sidebar and every other page answered with a back arrow — so moving from
 * `/discover` to `/settings` changed the whole frame, and nothing was ever where the last page
 * had taught the reader to look.
 *
 * The frame is the fixed part: rail, content, tab bar. The content region owns its scroll, so
 * a page header can stick to the thing it belongs to. `/setup` stays outside it: first run has
 * no places to go, and a rail offering five pages to somebody who has not chosen an engine is
 * a navigation bar over an empty product.
 */
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import NavRail from './NavRail'
import MobileTabs from './MobileTabs'

/** The chat scrolls its own transcript; a page scrolls the page. */
const OWNS_ITS_SCROLL = new Set(['/', '/chat'])

export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()

  if (pathname === '/setup') return <>{children}</>

  const owns = OWNS_ITS_SCROLL.has(pathname)

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-canvas">
      <NavRail />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div
          data-testid="shell-content"
          className={owns ? 'min-h-0 flex-1 overflow-hidden' : 'min-h-0 flex-1 overflow-y-auto'}
        >
          {children}
        </div>
        <MobileTabs />
      </div>
    </div>
  )
}
