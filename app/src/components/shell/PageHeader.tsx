/**
 * Ephe — S wave: app-shell building blocks (docs/BRAND.md, the Ephemora look).
 *
 * PageHeader: a large page heading + subtitle + an action slot
 * (refresh/settings/primary, as in the app-shell pattern). Pure
 * presentation — state and i18n come from the caller.
 *
 * A section header whose title repeats the surface's area title loses the heading,
 * not the text (`pageHeaderArea.ts`). The settings page uses it, where the tab label
 * and the section title were the same string twice in the outline ("Engine",
 * "Knowledge", "Appearance").
 */
import { useContext } from 'react'
import { PageHeaderAreaTitle } from './pageHeaderArea'

export default function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}) {
  const areaTitle = useContext(PageHeaderAreaTitle)
  // Same string as the area title: the view already announces it once.
  const repeatsAreaTitle = areaTitle !== null && areaTitle === title
  const Title = repeatsAreaTitle ? 'p' : 'h2'
  return (
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <Title
          data-testid="page-title"
          className="font-display text-2xl font-semibold tracking-tight text-foreground/95"
        >
          {title}
        </Title>
        {subtitle && (
          <p data-testid="page-subtitle" className="mt-1 text-ui-sm text-ink-faint">
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div data-testid="page-actions" className="flex shrink-0 items-center gap-2">
          {actions}
        </div>
      )}
    </div>
  )
}
