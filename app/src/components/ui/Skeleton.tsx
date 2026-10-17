import { cn } from '@/lib/utils'

/** P1-10: shimmer placeholder for loading states. `aria-hidden` — screen readers
 *  are shown nothing faked; `motion-reduce` switches the pulsing off for users
 *  sensitive to motion sickness (the Ephe norm).
 *
 *  The surface used to be a 7% white veil — practically invisible on the light
 *  paper ground, so in the light theme the placeholder showed nothing at all. A
 *  hairline is the quietest role that exists in both themes. */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse motion-reduce:animate-none rounded-md bg-hairline', className)}
      {...props}
    />
  )
}

export { Skeleton }
