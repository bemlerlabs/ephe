/** A shelf: one subject, one line about it, one row of entries that scrolls
 *  sideways. The row is the point — a shelf never turns a subject into a page. */
import { ArrowRight } from 'lucide-react'
import type { ReactNode } from 'react'
import './discover.css'

export function Shelf({
  testId,
  subject,
  title,
  lede,
  action,
  className = '',
  children,
}: {
  testId: string
  subject?: string
  title: string
  lede?: string
  action?: { label: string; testId: string; onClick: () => void }
  className?: string
  children: ReactNode
}) {
  return (
    <section data-testid={testId} data-subject={subject} className={className}>
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-display text-xl leading-tight tracking-tight text-foreground/95">
            <span aria-hidden="true" className="discover-dot h-1.5 w-1.5 shrink-0 rounded-full" />
            {title}
          </h3>
          {lede ? <p className="mt-1 text-ui-xs leading-relaxed text-ink-faint">{lede}</p> : null}
        </div>
        {action ? (
          <button
            type="button"
            data-testid={action.testId}
            onClick={action.onClick}
            className="focus-ring group inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-ui-xs text-ink-soft hover:text-foreground"
          >
            {action.label}
            <ArrowRight
              aria-hidden="true"
              className="h-3.5 w-3.5 transition-transform motion-safe:duration-fast group-hover:translate-x-0.5"
            />
          </button>
        ) : null}
      </div>
      <div
        role="group"
        aria-label={title}
        tabIndex={0}
        className="focus-ring -mx-4 mt-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden"
      >
        {children}
      </div>
    </section>
  )
}
