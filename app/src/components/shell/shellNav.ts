/**
 * Ephe — the destinations of the app frame, spelled once (shell, finding #61).
 *
 * The rail on a wide window and the tab bar on a phone read the same list, so a place cannot
 * appear in one and not the other. Membership is the app's own routes; a row that names no
 * route would be a control that goes nowhere.
 */
import type { ComponentType } from 'react'
import { Boxes, Brain, GitBranch, MessagesSquare, Settings, Store, Wrench } from 'lucide-react'

export interface ShellDestination {
  readonly id: string
  readonly path: string
  readonly labelKey: string
  readonly Icon: ComponentType<{ className?: string }>
  /** The rail marks a row active on a prefix, so a sub-page keeps its row lit. */
  readonly prefix: string
  /** Phones carry the five places a thumb reaches for; the rest are inside a page. */
  readonly onTabBar: boolean
}

export const SHELL_DESTINATIONS: readonly ShellDestination[] = [
  {
    id: 'task',
    path: '/',
    prefix: '/',
    labelKey: 'shell.navTask',
    Icon: MessagesSquare,
    onTabBar: true,
  },
  {
    id: 'tools',
    path: '/tools',
    prefix: '/tools',
    labelKey: 'shell.navTools',
    Icon: Wrench,
    onTabBar: true,
  },
  {
    id: 'discover',
    path: '/discover',
    prefix: '/discover',
    labelKey: 'shell.navDiscover',
    Icon: Store,
    onTabBar: true,
  },
  {
    id: 'workspaces',
    path: '/workspaces',
    prefix: '/workspaces',
    labelKey: 'shell.navWorkspaces',
    Icon: GitBranch,
    onTabBar: false,
  },
  {
    id: 'artifacts',
    path: '/artifacts',
    prefix: '/artifacts',
    labelKey: 'shell.navArtifacts',
    Icon: Boxes,
    onTabBar: false,
  },
  {
    id: 'knowledge',
    path: '/memory',
    prefix: '/memory',
    labelKey: 'shell.navKnowledge',
    Icon: Brain,
    onTabBar: true,
  },
  {
    id: 'settings',
    path: '/settings',
    prefix: '/settings',
    labelKey: 'shell.navSettings',
    Icon: Settings,
    onTabBar: true,
  },
]

/** The tab bar's subset, in order. */
export const TAB_BAR_DESTINATIONS = SHELL_DESTINATIONS.filter((one) => one.onTabBar)

/** The row a path belongs to. The longest prefix wins, so `/` only holds the chat. */
export function activeDestination(pathname: string): ShellDestination | undefined {
  const hits = SHELL_DESTINATIONS.filter(
    (one) =>
      one.prefix !== '/' && (pathname === one.prefix || pathname.startsWith(`${one.prefix}/`)),
  )
  if (hits.length === 0) {
    if (pathname === '/' || pathname === '/chat') return SHELL_DESTINATIONS[0]
    return undefined
  }
  return hits.reduce((best, one) => (one.prefix.length > best.prefix.length ? one : best))
}
