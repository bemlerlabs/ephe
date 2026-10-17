'use client'

/**
 * I3-V1: the control on the right of a settings row — type-safe from the register.
 *
 * Pulled out of sections-deep.tsx because every area (engine, audio, memory,
 * plugin store) needs the same four controls: a switch, a choice, a number with a
 * range, free text. One pattern, four shells, no section with its own handwriting.
 */
import { useTranslation } from 'react-i18next'
import Switch from './Switch'
import type { DeepField } from '@/types'

/**
 * A control of the register: square corners, one hairline as its edge, the canvas
 * as its ground, the value at the UI step in the mono face and set flush right so
 * every control of a column ends on the same axis. The radius and the filled
 * ground the old handwriting gave a control belong to the boxed register.
 */
const CONTROL_CLASS =
  'border border-hairline-strong bg-canvas px-2 py-1 text-right font-mono text-scale-ui text-ink outline-none focus-ring transition-colors'

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
        className={`${CONTROL_CLASS} min-w-32 max-lg:min-h-11`}
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
          className={`${CONTROL_CLASS} w-28 tabular-nums max-lg:min-h-11`}
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
      className={`${CONTROL_CLASS} w-60 max-md:w-32`}
    />
  )
}
