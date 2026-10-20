'use client'

/**
 * The register's grouped list and its rows — the one pattern every area is
 * built from.
 *
 * Native contract (docs/DESIGN.md, studio brief): an inset grouped list on the
 * forest canvas, neutral graphite surfaces, a 44 px row floor and 10-12 px
 * radii. A group title is a sentence above the card; the card is the only
 * frame a row gets. Component, prop and testid names are the register's index
 * (rowIndex.ts, rowInventory.test.ts) and stay unchanged.
 */
import type { ComponentType, HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** A path or an address the row edits: wide enough to read while typing. */
export const FIELD_COL = 'w-56'

/** A verb that can be pressed: a native text button. */
export const VERB_BUTTON =
  'focus-ring inline-flex min-h-8 max-w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1 text-scale-ui text-ink-soft transition-colors hover:bg-surface-interactive hover:text-ink disabled:opacity-40 pointer-coarse:min-h-11'

export interface SettingsGroupProps {
  title?: string
  /** One purpose line for the whole group — it does not caption each row on its own. */
  description?: string
  icon?: ComponentType<{ className?: string }>
  /** An action that concerns ALL rows of the group — not a single one. */
  action?: ReactNode
  testid?: string
  children: ReactNode
}

export function SettingsGroup({
  title,
  description,
  icon: Icon,
  action,
  testid,
  children,
}: SettingsGroupProps) {
  return (
    <section className="space-y-2" data-testid={testid}>
      {(title || action) && (
        <div className="flex items-end justify-between gap-3 px-1">
          <div className="min-w-0">
            {title && (
              <h4 className="flex items-center gap-1.5 text-scale-ui font-medium text-ink">
                {Icon && (
                  <Icon className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
                )}
                <span className="truncate">{title}</span>
              </h4>
            )}
            {description && <p className="pt-0.5 text-scale-data text-ink-faint">{description}</p>}
          </div>
          {action}
        </div>
      )}
      <div className="divide-y divide-hairline overflow-hidden rounded-xl border border-hairline bg-surface">
        {children}
      </div>
    </section>
  )
}

export interface SettingsRowProps {
  icon?: ComponentType<{ className?: string }>
  title: string
  /** What the value changes — not what it is called. */
  description?: string
  children?: ReactNode
  /** A done state: the row stays readable, but steps back. */
  muted?: boolean
  testid?: string
}

export function SettingsRow({
  icon: Icon,
  title,
  description,
  children,
  muted,
  testid,
}: SettingsRowProps) {
  return (
    <div
      data-testid={testid}
      className={cn(
        'flex min-h-11 flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4',
        muted && 'opacity-60',
      )}
    >
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'flex items-center gap-2 text-scale-ui',
            muted ? 'text-ink-faint' : 'text-ink',
          )}
        >
          {Icon && <Icon className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />}
          <span className="truncate">{title}</span>
        </p>
        {description && (
          <p
            data-testid={testid ? `${testid}-desc` : undefined}
            className="pt-0.5 text-scale-data text-ink-faint"
          >
            {description}
          </p>
        )}
      </div>
      {children && (
        <div className="flex shrink-0 items-center justify-end gap-2 max-sm:w-full">{children}</div>
      )}
    </div>
  )
}

export interface SettingValueProps extends HTMLAttributes<HTMLSpanElement> {
  /** The one accent is for what is happening at this moment, so a value that
   *  describes a stored state keeps ink. */
  now?: boolean
}

/** The value in the right column: sentence-face ink, right-aligned so values
 *  of adjacent rows meet on one edge without a mono column. */
export function SettingValue({ now = false, className, children, ...props }: SettingValueProps) {
  return (
    <span
      className={cn(
        'shrink-0 max-w-64 truncate text-right text-scale-ui tabular-nums',
        now ? 'text-brand-deep' : 'text-ink-soft',
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}

/** The verb at the row's right edge: the word for the state, or the control that
 *  acts on the row. */
export function SettingVerb({ className, children, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn('flex shrink-0 items-center justify-end gap-2 text-scale-ui', className)}
      {...props}
    >
      {children}
    </span>
  )
}
