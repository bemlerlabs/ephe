import { cn } from '@/lib/utils'
import { cva, type VariantProps } from 'class-variance-authority'

const badgeVariants = cva(
  'inline-flex items-center rounded-full px-3 py-1 text-ui-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-brand/10 text-brand-deep border border-brand/20',
        outline: 'border border-brand/20 text-brand-deep',
        success: 'bg-status-success/20 text-status-success border border-status-success/30',
        warning: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
        destructive: 'bg-status-danger/20 text-status-danger border border-status-danger/30',
        info: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
