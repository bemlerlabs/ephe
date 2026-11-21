import type { Page } from '@playwright/test'

/** The two collapsible nav tiers of the sidebar, named by the id the rail renders. */
export type SidebarTier = 'tools' | 'more'

/**
 * Open a sidebar tier before clicking a row inside it.
 *
 * Register #71 grouped the rail into three tiers (primary headless, then "Tools &
 * Capabilities", then the rest) and the two lower ones start closed, so a spec
 * that clicks `sidebar-action-files` right away finds the row in the document but
 * hidden — a real browser refuses that click while jsdom would not, which is why
 * only the live specs can see it. Opening is idempotent: the state is a stored
 * preference, so a second run in the same profile starts with the tier open.
 */
export async function openTier(page: Page, tier: SidebarTier): Promise<void> {
  const head = page.getByTestId(`sidebar-tier-${tier}-toggle`)
  if ((await head.count()) === 0) return
  if ((await head.getAttribute('aria-expanded')) !== 'true') {
    await head.click()
    await page.waitForTimeout(150)
  }
}
