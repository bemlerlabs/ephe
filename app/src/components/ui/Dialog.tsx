import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { forwardRef } from 'react'

const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogPortal = DialogPrimitive.Portal
const DialogClose = DialogPrimitive.Close

const DialogOverlay = forwardRef<HTMLDivElement, DialogPrimitive.DialogOverlayProps>(
  ({ className, ...props }, ref) => (
    <DialogPrimitive.Overlay
      ref={ref}
      className={cn(
        'fixed inset-0 z-overlay bg-canvas/80 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        className,
      )}
      {...props}
    />
  ),
)
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

const DialogContent = forwardRef<HTMLDivElement, DialogPrimitive.DialogContentProps>(
  ({ className, children, ...props }, ref) => (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          // Edge inset + scroll: a centred dialog without a max-height runs off the
          // top on a phone (fixed + translate-y-[-50%]), and w-full touches the
          // screen edges. 90dvh follows the mobile toolbar, overflow-y-auto keeps
          // tall content reachable.
          'fixed left-[50%] top-[50%] z-overlay w-[calc(100vw-2rem)] max-w-lg max-h-[90dvh] overflow-y-auto translate-x-[-50%] translate-y-[-50%] float-surface p-6 forest-glow-strong animate-in fade-in-0 zoom-in-95',
          className,
        )}
        data-float="3"
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100 transition-opacity">
          <X className="h-4 w-4 text-foreground/60" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPortal>
  ),
)
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />
)
DialogHeader.displayName = 'DialogHeader'

const DialogTitle = forwardRef<HTMLHeadingElement, DialogPrimitive.DialogTitleProps>(
  ({ className, ...props }, ref) => (
    <DialogPrimitive.Title
      ref={ref}
      className={cn('text-ui-lg font-semibold text-foreground', className)}
      {...props}
    />
  ),
)
DialogTitle.displayName = DialogPrimitive.DialogTitle.displayName

export { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogClose }
