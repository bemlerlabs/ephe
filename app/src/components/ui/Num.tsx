import { cn } from '@/lib/utils'
import { forwardRef } from 'react'

/** Every number in this interface is set here: JetBrains Mono, tabular figures,
 *  right-aligned on one shared column, so digits line up between rows. `now` is
 *  the one accent — a number carries it only when it describes what is happening
 *  NOW. The size and the ink sit on an inner element on purpose: tailwind-merge
 *  reads every custom text-* step as a colour and drops the size when size and
 *  colour meet in one merged string (LoadingRow carries the same note). */
const COL = {
  1: 'w-[var(--num-col-1)]',
  2: 'w-[var(--num-col-2)]',
  3: 'w-[var(--num-col-3)]',
} as const

/** The column a number sits in: 1 is the row column, 2 and 3 are the wider ones
 *  the direction draws for a step counter and for a full status line. */
export type NumCol = keyof typeof COL

export interface NumProps extends React.HTMLAttributes<HTMLSpanElement> {
  col?: NumCol
  now?: boolean
}

const Num = forwardRef<HTMLSpanElement, NumProps>(
  ({ className, col = 1, now = false, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn('inline-block shrink-0 whitespace-nowrap text-right', COL[col], className)}
      {...props}
    >
      <span
        className={
          now
            ? 'font-mono tabular-nums text-scale-data text-brand-deep'
            : 'font-mono tabular-nums text-scale-data text-ink-faint'
        }
      >
        {children}
      </span>
    </span>
  ),
)
Num.displayName = 'Num'

export { Num }
