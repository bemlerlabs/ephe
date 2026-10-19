'use client'

/**
 * I3-V1: the switch of the settings surface.
 *
 * Before, one and the same thing had three handwritings: a `true/false` segment in
 * the expert register, a text pill ("An"/"Aus") in the plugin store, and the iOS // language-gate: ignore — "An"/"Aus" are the German on/off labels the UI renders (locales/de.json:532-533)
 * switch only at KeepAwake. One control, one shell is the rule: the switch here IS
 * that shell — role, state and keyboard are defined once, not per section.
 */
import { useCallback } from 'react'

export default function Switch({
  checked,
  onChange,
  label,
  testid,
  disabled = false,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  /** A complete aria-label — the switch itself carries no text. */
  label: string
  testid?: string
  disabled?: boolean
}) {
  const handleKeys = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault()
        if (!disabled) onChange(!checked)
      }
    },
    [checked, disabled, onChange],
  )

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      onKeyDown={handleKeys}
      data-testid={testid}
      className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors duration-base focus-ring disabled:cursor-not-allowed disabled:opacity-40 ${
        checked ? 'border-brand/40 bg-brand/70' : 'border-control bg-surface'
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-base ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  )
}
