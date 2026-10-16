/**
 * Ephe — S wave: the Section container (app-shell pattern): a section title
 * + an optional action in the title row + content. Keeps content pages rhythmic.
 */
export default function Section({
  title,
  action,
  children,
  testid,
}: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
  testid?: string
}) {
  return (
    <section data-testid={testid} className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-ui-base font-semibold text-foreground/85">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  )
}
