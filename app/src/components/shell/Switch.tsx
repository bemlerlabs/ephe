'use client'

/**
 * The switch of the settings surface.
 *
 * One control, one shell: role, state and keyboard are defined here rather than
 * in every section. The track stays neutral — a stored selection is not a live
 * action, so the accent does not move with it. On and off differ by the knob's
 * position and the track's graphite step; the brand fill stays out.
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
        checked ? 'border-ink bg-ink' : 'border-control bg-surface-interactive'
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full transition-transform duration-base ${
          checked ? 'translate-x-5 bg-canvas' : 'translate-x-0 bg-ink-faint'
        }`}
      />
    </button>
  )
}
