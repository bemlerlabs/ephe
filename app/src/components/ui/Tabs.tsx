import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '@/lib/utils'
import { forwardRef } from 'react'

const Tabs = TabsPrimitive.Root

const TabsList = forwardRef<HTMLDivElement, TabsPrimitive.TabsListProps>(
  ({ className, ...props }, ref) => (
    <TabsPrimitive.List
      ref={ref}
      className={cn(
        'inline-flex items-center gap-1 rounded-lg bg-secondary p-1 text-muted-foreground',
        className,
      )}
      {...props}
    />
  ),
)
TabsList.displayName = TabsPrimitive.List.displayName

const TabsTrigger = forwardRef<HTMLButtonElement, TabsPrimitive.TabsTriggerProps>(
  ({ className, ...props }, ref) => (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-2.5 py-1 text-ui-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none data-[state=active]:bg-background data-[state=active]:text-foreground',
        className,
      )}
      {...props}
    />
  ),
)
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName

const TabsContent = forwardRef<HTMLDivElement, TabsPrimitive.TabsContentProps>(
  ({ className, ...props }, ref) => (
    <TabsPrimitive.Content
      ref={ref}
      className={cn('mt-2 focus-visible:outline-none', className)}
      {...props}
    />
  ),
)
TabsContent.displayName = TabsPrimitive.Content.displayName

export { Tabs, TabsList, TabsTrigger, TabsContent }
