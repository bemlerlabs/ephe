'use client'

/**
 * The control on the right of a settings row — type-safe from the register.
 *
 * Four shells, one pattern: a switch, a choice, a number with a range, free
 * text. Native contract: a neutral graphite field on the grouped card, 10-12 px
 * radii, sentence-case labels and the one accent only for a live or primary
 * action. The value is never dressed in a mono column.
 */
import { useTranslation } from 'react-i18next'
import Switch from './Switch'
import type { DeepField } from '@/types'

export const CONTROL_CLASS =
  'h-9 rounded-lg border border-control bg-surface-raised px-3 text-scale-ui text-ink outline-none transition-colors hover:border-hairline-strong focus-ring'

/** A neutral segmented choice for a small enum — selection is a graphite step,
 *  so the one accent stays for the live action. */
export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  testid,
}: {
  label: string
  value: T | null
  options: { id: T; label: string }[]
  onChange: (id: T) => void
  testid?: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      data-testid={testid}
      className="flex flex-wrap gap-0.5 rounded-lg bg-surface p-0.5"
    >
      {options.map((option) => {
        const selected = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.id)}
            className={`min-h-7 rounded-md px-2.5 py-1 text-scale-data font-medium transition-colors pointer-coarse:min-h-11 ${
              selected
                ? 'bg-surface-interactive text-ink'
                : 'text-ink-soft hover:bg-surface-interactive hover:text-ink'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export default function SettingControl({
  field,
  value,
  label,
  onCommit,
}: {
  field: DeepField
  value: string | number | boolean
  /** The field's display text — used to keep the control readable. */
  label: string
  onCommit: (next: string | number | boolean) => void
}) {
  const id = `setting-field-${field.key}`
  const { i18n } = useTranslation()
  const isDe = (i18n?.language || 'de').startsWith('de')
  /** I6-3: value text from the register; without a label the identifier stays. */
  const optionText = (opt: string) => {
    const hit = field.optionLabels?.find((o) => o.value === opt)
    return hit ? (isDe ? hit.label : hit.labelEn) : opt
  }

  if (field.type === 'bool') {
    return (
      <Switch
        checked={String(value) === 'true'}
        onChange={onCommit}
        label={label}
        testid={`setting-switch-${field.key}`}
      />
    )
  }

  if (field.type === 'select') {
    return (
      <select
        id={id}
        value={String(value)}
        onChange={(e) => onCommit(e.target.value)}
        aria-label={label}
        data-testid={`setting-select-${field.key}`}
        className={`${CONTROL_CLASS} min-w-32 pr-8 max-lg:min-h-11`}
      >
        {(field.options ?? []).map((opt) => (
          <option key={opt} value={opt}>
            {optionText(opt)}
          </option>
        ))}
      </select>
    )
  }

  if (field.type === 'number') {
    return (
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={field.min}
          max={field.max}
          step={field.step ?? 'any'}
          value={String(value)}
          onChange={(e) => onCommit(e.target.value === '' ? '' : Number(e.target.value))}
          aria-label={label}
          data-testid={`setting-number-${field.key}`}
          className={`${CONTROL_CLASS} w-24 text-right tabular-nums max-lg:min-h-11`}
        />
        {field.min !== undefined && field.max !== undefined && (
          <span className="text-scale-data text-ink-faint tabular-nums">
            {field.min}–{field.max}
          </span>
        )}
      </div>
    )
  }

  return (
    <input
      id={id}
      type="text"
      value={String(value)}
      onChange={(e) => onCommit(e.target.value)}
      aria-label={label}
      data-testid={`setting-text-${field.key}`}
      className={`${CONTROL_CLASS} w-56 max-md:w-40`}
    />
  )
}
