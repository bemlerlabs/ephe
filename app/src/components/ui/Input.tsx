import { cn } from '@/lib/utils'
import { forwardRef, InputHTMLAttributes } from 'react'

type InputProps = InputHTMLAttributes<HTMLInputElement>

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = 'text', ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'glass-control focus-ring rounded-xl px-4 py-3 text-ui-sm text-foreground placeholder:text-ink-faint transition-all duration-base',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export { Input }
