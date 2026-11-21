/**
 * S2 — one row of the model picker.
 *
 * The name if the endpoint gave one, otherwise the tag in mono (a raw id is a raw id,
 * and the face of it tells the reader that). Price and context print an em-dash when the
 * engine did not say, and a capability chip is drawn only for a fact the engine stated —
 * an unknown tool claim has no chip at all, which is the difference between "not tested"
 * and "no".
 */
import { Star, StarOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { UNKNOWN_CELL, type ModelRow } from './modelPickerTypes'
import { formatContext, formatPricePair } from './modelPickerQuery'

interface ModelPickerRowProps {
  row: ModelRow
  /** Keyboard cursor sits on this row. */
  active: boolean
  selected: boolean
  favorite: boolean
  optionId: string
  testId: string
  onSelect: () => void
  onToggleFavorite: () => void
}

function Capability({
  kind,
  label,
  state,
}: {
  kind: string
  label: string
  state: boolean | null
}) {
  if (state === null) return null
  return (
    <span
      className={`shrink-0 rounded px-1 py-0.5 font-mono text-ui-2xs ${
        state ? 'bg-brand/15 text-brand-deep' : 'bg-surface text-ink-faint'
      }`}
      data-testid={`model-chip-${kind}`}
      data-state={state ? 'yes' : 'no'}
    >
      {state ? label : `¬${label}`}
    </span>
  )
}

export function ModelPickerRow({
  row,
  active,
  selected,
  favorite,
  optionId,
  testId,
  onSelect,
  onToggleFavorite,
}: ModelPickerRowProps) {
  const { t } = useTranslation()
  const title = row.displayName || row.id
  const beside = row.hint ?? row.endpoint ?? ''
  const isTag = !row.displayName
  const price = formatPricePair(row.meta)
  const priceText = price
    ? t('modelPicker.perMillion', {
        pair: t('modelPicker.pricePair', { in: price.in, out: price.out }),
      })
    : null
  const context = formatContext(row.meta.contextWindow)

  return (
    <div
      role="option"
      id={optionId}
      aria-selected={selected}
      aria-current={selected ? 'true' : undefined}
      aria-disabled={row.selectable ? undefined : true}
      data-testid={testId}
      data-model-id={row.id}
      // The row is the target, the two controls inside keep their own jobs: a click
      // that landed on a button is that button's, everything else selects the row.
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest('button')) onSelect()
      }}
      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors max-lg:min-h-11 ${
        active ? 'bg-brand/20' : 'hover:bg-surface'
      }`}
    >
      <button
        type="button"
        disabled={!row.selectable}
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-2 text-left focus-ring"
        title={beside ? `${title} — ${beside}` : title}
      >
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-ui-xs font-medium text-foreground ${isTag ? 'font-mono font-normal' : ''}`}
          >
            {title}
          </span>
          <span className="block truncate font-mono text-ui-2xs text-ink-faint">
            {[row.hint ?? row.group, context ?? UNKNOWN_CELL, priceText ?? UNKNOWN_CELL]
              .filter(Boolean)
              .join(' · ')}
          </span>
          {/* S3: the engine stated no tools, so the row says what that means for the
              run rather than leaving a negated chip to be interpreted. */}
          {row.meta.supportsTools === false && (
            <span
              className="block truncate text-ui-2xs text-ink-faint"
              data-testid="model-answer-only"
            >
              {t('modelPicker.answerOnly')}
            </span>
          )}
        </span>
      </button>
      <span className="flex shrink-0 items-center gap-1">
        <Capability kind="free" label={t('modelPicker.free')} state={row.meta.isFree} />
        <Capability kind="tools" label={t('modelPicker.tools')} state={row.meta.supportsTools} />
        <Capability kind="vision" label={t('modelPicker.vision')} state={row.meta.supportsVision} />
        <button
          type="button"
          onClick={onToggleFavorite}
          data-testid={`${testId}-favorite`}
          aria-pressed={favorite}
          aria-label={t(favorite ? 'modelPicker.unfavor' : 'modelPicker.favor')}
          className="shrink-0 rounded p-1 text-ink-faint transition-colors hover:text-foreground focus-ring"
        >
          {favorite ? (
            <Star className="h-3.5 w-3.5 fill-current text-brand" aria-hidden="true" />
          ) : (
            <StarOff className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </button>
      </span>
    </div>
  )
}
