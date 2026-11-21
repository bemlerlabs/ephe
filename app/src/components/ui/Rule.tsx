import { cn } from '@/lib/utils'
import { forwardRef } from 'react'

/** The direction draws structure with rules and indents, not with a border plus
 *  a shadow on a box. Three line weights exist and no fourth: a 1px hairline for
 *  structure, 2px hairline-strong for the selected edge, and 2px brand for what
 *  is happening NOW — the one accent. A rule is placed between two things rather
 *  than on both edges of one, so neighbours can never double a line. */
type RuleTone = 'rule' | 'selected' | 'now'
type RuleOrientation = 'horizontal' | 'vertical'

const TONE: Record<RuleTone, string> = {
  rule: 'bg-hairline',
  selected: 'bg-hairline-strong',
  now: 'bg-brand',
}

export interface RuleProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: RuleOrientation
  tone?: RuleTone
}

const Rule = forwardRef<HTMLDivElement, RuleProps>(
  ({ className, orientation = 'horizontal', tone = 'rule', ...props }, ref) => {
    const vertical = orientation === 'vertical'
    const thin = tone === 'rule'
    return (
      <div
        ref={ref}
        aria-hidden="true"
        className={cn(
          'shrink-0',
          vertical ? 'self-stretch' : 'w-full',
          thin ? (vertical ? 'w-px' : 'h-px') : vertical ? 'w-0.5' : 'h-0.5',
          TONE[tone],
          className,
        )}
        {...props}
      />
    )
  },
)
Rule.displayName = 'Rule'

export { Rule }
