'use client'

/**
 * The plugin master switch.
 *
 * The committed state comes from the backend; the knob follows the requested
 * state while a request is pending, a second click is ignored, and a failure
 * returns the knob to the committed position with a reason in the row. The
 * switch never reports success before the registry confirms it.
 */
import { useEffect, useState } from 'react'

import Switch from '@/components/shell/Switch'

export interface PluginSwitchLabels {
  on: string
  off: string
  enabling: string
  disabling: string
  failed: string
}

export default function PluginSwitch({
  name,
  checked,
  onToggle,
  labels,
  testid,
  errorTestid,
  describeError,
  disabled = false,
}: {
  name: string
  checked: boolean
  onToggle: (next: boolean) => Promise<void> | void
  labels: PluginSwitchLabels
  testid?: string
  errorTestid?: string
  describeError?: (reason: unknown, fallback: string) => string
  disabled?: boolean
}) {
  const [pending, setPending] = useState<'enabling' | 'disabling' | null>(null)
  const [requested, setRequested] = useState(checked)
  const [error, setError] = useState('')

  useEffect(() => {
    setRequested(checked)
  }, [checked])

  const request = async (next: boolean) => {
    if (pending || disabled) return
    setPending(next ? 'enabling' : 'disabling')
    setRequested(next)
    setError('')
    try {
      await onToggle(next)
    } catch (reason) {
      setRequested(checked)
      const fallback = labels.failed
      const message = describeError
        ? describeError(reason, fallback)
        : reason instanceof Error && reason.message
          ? reason.message
          : fallback
      setError(message || fallback)
    } finally {
      setPending(null)
    }
  }

  const stateLabel = pending ? labels[pending] : requested ? labels.on : labels.off
  const accessibleName = `${name}, ${requested ? labels.on : labels.off}${
    pending ? `, ${labels[pending]}` : ''
  }`

  return (
    <div className="flex shrink-0 flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className={`text-ui-xs font-medium ${requested ? 'text-brand-deep' : 'text-ink-faint'}`}
        >
          {stateLabel}
        </span>
        <Switch
          checked={requested}
          onChange={(next) => void request(next)}
          label={accessibleName}
          testid={testid}
          disabled={disabled}
          busy={pending !== null}
          expandedHitArea
        />
      </div>
      {error && (
        <p
          role="alert"
          data-testid={errorTestid}
          className="max-w-40 text-right text-ui-2xs text-status-danger"
        >
          {error}
        </p>
      )}
    </div>
  )
}
