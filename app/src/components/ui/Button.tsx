import { cn } from '@/lib/utils'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef } from 'react'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-xl font-medium transition-all duration-base ease-organic focus-ring disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        primary: 'bg-brand hover:bg-brand-glow text-black forest-glow',
        secondary: 'glass-control hover:bg-brand/10 text-foreground',
        ghost: 'hover:bg-brand/5 text-foreground/70 hover:text-foreground',
        destructive: 'bg-status-danger hover:bg-status-danger text-foreground',
        link: 'text-brand hover:text-brand underline underline-offset-4',
      },
      size: {
        sm: 'h-8 px-3 text-ui-xs gap-1.5',
        md: 'h-10 px-4 text-ui-sm gap-2',
        lg: 'h-12 px-6 text-ui-base gap-2.5',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  as?: 'button' | 'a'
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, as: Tag = 'button', ...props }, ref) => {
    return (
      // @ts-expect-error — a polymorphic tag (button | a) with forwardRef
      <Tag className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />
    )
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
