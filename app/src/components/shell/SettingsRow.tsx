'use client'

/**
 * The register's section head and its rows — the one pattern every area is built
 * from.
 *
 * The direction (visions/D-synthese, settings-ink.html) rules this surface: a
 * section is its name at the UI step with a doubled rule under it, a row is a
 * label at 13 with the explanation at 11 below, and the value and the verb end
 * on the right edge in the direction's own columns — 176 px for a value, 112 px
 * for a verb. Both widths are the 44 and 28 spacing steps, so no raw length
 * enters a call site and the value column lands on the same axis as
 * `--num-col-2`.
 *
 * The doubled rule is the grouping device this surface's measurement chose: the
 * sheet's own 1 px hairline drawn twice with a 2 px gap between, so a section
 * boundary reads heavier than the single hairline dividing two rows while no
 * second line weight and no fill is spent. The device dies the moment its own
 * name scrolls out of the viewport, so the head is sticky inside the register's
 * scroll column. The canvas under the head is what makes that occlusion work:
 * without a fill the rows would show through the name. Its cost is the band it
 * holds open, measured at 34 px for a head without a description and 54 px with
 * one.
 *
 * The contract the register is indexed by is untouched: `SettingsGroup`,
 * `SettingsRow`, `title` and `description` keep their names and their shapes,
 * because ./model/rowIndex.ts and rowInventory.test.ts read the sections through
 * them and twenty section files build their rows with them. The anatomy inside
 * changed, so every one of those rows moved onto the direction at once.
 */
import type { ComponentType, HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Rule } from '@/components/ui'

/** The value column of a stored value: the direction's 176 px data column. */
const VALUE_COL = 'w-44'
/** The verb column, as a fixed width rather than a minimum: a longer verb would
 *  otherwise widen its own slot and push that row's value off the line every other
 *  value sits on. 128 px is the mockup's 112 px plus the padding and the edge a
 *  pressable verb carries, so the longest word of the register ("Change folder…")
 *  fits without wrapping. Every value of a group carries the slot, empty where the
 *  row has no verb. */
const VERB_COL = 'w-32'

/** The column an EDITABLE value sits in: 240 px, because a path or an address has
 *  to be readable while it is being typed. It ends on the same line as the data
 *  column of the row above, since the verb slot of the same width follows both. */
export const FIELD_COL = 'w-60'

/** A verb that can be pressed: a word at the data step on the 44 px touch floor
 *  below the large breakpoint, square corners, no fill beyond the canvas. */
export const VERB_BUTTON =
  'focus-ring inline-flex min-h-6 max-w-full items-center justify-center gap-1.5 whitespace-nowrap border border-hairline-strong px-2 py-0.5 text-scale-data text-ink-soft transition-colors hover:border-ink-faint hover:text-ink disabled:opacity-40 max-lg:min-h-11'

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
    <section className="flex flex-col" data-testid={testid}>
      <div className="sticky top-0 z-sticky bg-canvas">
        {/* The sticky offset resolves against the scroll column's padded content
            edge, measured at 16 px below the column's own top edge, so a pinned
            head leaves that strip open for the rows scrolling past behind it.
            This band paints the strip in the canvas, and at rest it covers the
            16 px gap the sections keep between each other. */}
        <div className="absolute -top-4 left-0 h-4 w-full bg-canvas" aria-hidden="true" />
        <Rule />
        <div className="flex items-center justify-between gap-2 pt-1.5 pb-1">
          {title && (
            <h4 className="flex min-w-0 items-center gap-1.5 text-scale-ui text-ink">
              {Icon && <Icon className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />}
              <span className="truncate">{title}</span>
            </h4>
          )}
          {action}
        </div>
        <Rule />
        <Rule className="mt-0.5" />
        {description && <p className="pt-1 text-scale-data text-ink-faint">{description}</p>}
      </div>
      <div className="divide-y divide-hairline">{children}</div>
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
    <div data-testid={testid} className="flex items-start gap-4 py-2.5">
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'flex items-center gap-1.5 text-scale-ui',
            muted ? 'text-ink-faint line-through' : 'text-ink',
          )}
        >
          {Icon && <Icon className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />}
          <span className="truncate">{title}</span>
        </p>
        {description && (
          <p
            data-testid={testid ? `${testid}-desc` : undefined}
            className={cn('pt-1 text-scale-data text-ink-faint', muted && 'opacity-60')}
          >
            {description}
          </p>
        )}
      </div>
      {children && <div className="flex shrink-0 items-center justify-end gap-3">{children}</div>}
    </div>
  )
}

export interface SettingValueProps extends HTMLAttributes<HTMLSpanElement> {
  /** The one accent is for what is happening at this moment, so a value that
   *  describes a stored state keeps ink. */
  now?: boolean
}

/** The value in the right column: the data step in the mono face, right-aligned
 *  on a column two rows share, so digits and paths line up down the surface. */
export function SettingValue({ now = false, className, children, ...props }: SettingValueProps) {
  return (
    <span
      className={cn(
        'shrink-0 truncate text-right font-mono text-scale-data tabular-nums',
        VALUE_COL,
        now ? 'text-brand-deep' : 'text-ink-faint',
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
      className={cn('flex shrink-0 items-center justify-end text-scale-ui', VERB_COL, className)}
      {...props}
    >
      {children}
    </span>
  )
}
