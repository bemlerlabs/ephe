export { default as AppShell } from './AppShell'
// W1-4: the overlay dock is loaded by its own path (`./OverlayHost`) and stays out of
// this barrel. A re-export here is a static edge the entry graph follows, and the module
// carries a stylesheet, so its CSS would ride the entry sheet again.
export { default as NavRail } from './NavRail'
export { default as MobileTabs } from './MobileTabs'
export { SHELL_DESTINATIONS, TAB_BAR_DESTINATIONS, activeDestination } from './shellNav'
export type { ShellDestination } from './shellNav'
