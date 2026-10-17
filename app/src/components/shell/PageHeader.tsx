/**
 * Ephe — S wave: app-shell building blocks (docs/BRAND.md, the Ephemora look).
 *
 * PageHeader: a large page heading + subtitle + an action slot
 * (refresh/settings/primary, as in the app-shell pattern). Pure
 * presentation — state and i18n come from the caller.
 */
export default function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <h2
          data-testid="page-title"
          className="font-display text-2xl font-semibold tracking-tight text-foreground/95"
        >
          {title}
        </h2>
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
