import * as SeparatorPrimitive from '@radix-ui/react-separator'
import { cn } from '@/lib/utils'
import { forwardRef } from 'react'

const Separator = forwardRef<HTMLDivElement, SeparatorPrimitive.SeparatorProps>(
  ({ className, orientation = 'horizontal', decorative = true, ...props }, ref) => (
    <SeparatorPrimitive.Root
      ref={ref}
      decorative={decorative}
      orientation={orientation}
      className={cn(
        'shrink-0 bg-border',
        orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
        className,
      )}
      {...props}
    />
  ),
)
Separator.displayName = SeparatorPrimitive.Root.displayName

export { Separator }
