import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/** The one loading row the dashboard draws: a brand spinner beside a faint label.
 *
 *  Loading used to be drawn six ways across the surfaces — a colourless 12px
 *  spinner in the file tree, a half-opacity brand ring in the settings, a bare
 *  text line in five panels, a full brand ring on the data pages. Same icon,
 *  same token, same voice now. The icon is aria-hidden because the label already
 *  carries the state, and `motion-reduce` stops the spin for users who ask for
 *  less motion (the Ephe norm, as in Skeleton). The label token sits on its own
 *  element: `cn` merges `text-ui-xs` and `text-ink-faint` as one colour group,
 *  so a single className would silently drop the size. */
export function LoadingRow({
  label,
  className,
  ...props
}: { label: string } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex items-center gap-2', className)} {...props}>
      <Loader2
        aria-hidden="true"
        className="h-4 w-4 shrink-0 animate-spin text-brand motion-reduce:animate-none"
      />
      <span className="text-ui-xs text-ink-faint">{label}</span>
    </div>
  )
}
