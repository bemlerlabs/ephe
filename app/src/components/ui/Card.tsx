import { cn } from '@/lib/utils'
import { forwardRef } from 'react'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  hover?: boolean
}

const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, hover = false, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'glass-reading rounded-2xl p-6 transition-all duration-slow',
        hover && 'hover:bg-brand/5 hover:border-brand/20 hover:forest-glow cursor-pointer',
        className,
      )}
      {...props}
    />
  ),
)
Card.displayName = 'Card'

export { Card }
