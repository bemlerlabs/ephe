import { cn } from '@/lib/utils'
import { Rule } from './Rule'

/** What a card used to be. A section is a title at the one title size, the rule
 *  underneath it, and a 13px line of explanation in the UI size — no box, no
 *  radius, no shadow, and indentation carries the nesting that the box used to
 *  carry. `now` turns the rule into the one accent, for the section that is
 *  running. */
export interface SectionHeadProps extends React.HTMLAttributes<HTMLElement> {
  title: string
  hint?: string
  now?: boolean
}

const TITLE = 'text-scale-title text-ink'
const HINT = 'pt-2 text-scale-ui text-ink-faint'

function SectionHead({
  className,
  title,
  hint,
  now = false,
  children,
  ...props
}: SectionHeadProps) {
  return (
    <section className={cn('flex flex-col', className)} {...props}>
      <h2 className={TITLE}>{title}</h2>
      <Rule className="mt-2.5" tone={now ? 'now' : 'rule'} />
      {hint ? <p className={HINT}>{hint}</p> : null}
      {children}
    </section>
  )
}

export { SectionHead }
