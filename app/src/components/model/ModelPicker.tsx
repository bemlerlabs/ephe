/**
 * S2 — the one model picker. Three hosts, one behaviour.
 *
 * Setup, the engine settings and the composer chip all used to render their own list of
 * models, each with its own subset of the rules. This is the frame the first two mount:
 * a trigger that keeps the host's anchor, and the panel — anchored on desktop, a
 * full-screen sheet with a visible close control below 768 px. The body itself lives in
 * `ModelPickerPanel`, because the composer frames it differently.
 */
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronDown } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/Dialog'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import type { ModelRow } from './modelPickerTypes'
import { ModelPickerPanel } from './ModelPickerPanel'

export interface ModelPickerProps {
  rows: ModelRow[]
  /** The chosen tag; '' means nothing chosen yet. */
  value: string
  onChange: (id: string) => void
  /** Host anchor, kept from the control this replaces. */
  testId: string
  id?: string
  label: string
  placeholder?: string
  disabled?: boolean
  loading?: boolean
  error?: string | null
  className?: string
}

export function ModelPicker({
  rows,
  value,
  onChange,
  testId,
  id,
  label,
  placeholder,
  disabled = false,
  loading = false,
  error = null,
  className = '',
}: ModelPickerProps) {
  const { t } = useTranslation()
  const phone = useMediaQuery('(max-width: 767px)')
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const selected = useMemo(() => rows.find((row) => row.id === value) ?? null, [rows, value])

  const close = (returnFocus: boolean) => {
    setOpen(false)
    if (returnFocus) triggerRef.current?.focus()
  }

  const choose = (row: ModelRow) => {
    onChange(row.id)
    close(true)
  }

  const panel = (
    <ModelPickerPanel
      rows={rows}
      value={value}
      onChoose={choose}
      onClose={close}
      testId={testId}
      label={label}
      placeholder={placeholder}
      loading={loading}
      error={error}
      sheet={phone}
    />
  )

  return (
    <div className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        data-testid={testId}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? close(false) : setOpen(true))}
        className="w-full rounded-xl border border-control bg-input px-4 py-3 text-left text-ui-sm text-foreground transition-colors hover:bg-surface focus-ring disabled:opacity-40 max-lg:min-h-11"
      >
        <span className="flex items-center gap-2">
          {selected ? (
            <Check className="h-3.5 w-3.5 shrink-0 text-brand" aria-hidden="true" />
          ) : (
            <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          )}
          <span className="min-w-0 flex-1 truncate">
            {selected
              ? selected.displayName || selected.id
              : loading
                ? t('modelPicker.loading')
                : (placeholder ?? t('modelPicker.choose'))}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-ink-faint" aria-hidden="true" />
        </span>
      </button>

      {open && phone && (
        <Dialog open onOpenChange={(next) => (next ? setOpen(true) : close(true))}>
          <DialogContent className="fixed inset-0 left-0 top-0 flex max-h-full w-full max-w-none translate-x-0 translate-y-0 flex-col overflow-hidden rounded-none p-0">
            <DialogTitle className="sr-only">{label}</DialogTitle>
            {panel}
          </DialogContent>
        </Dialog>
      )}
      {open && !phone && (
        <div
          className="absolute z-modal mt-1 flex max-h-96 w-full min-w-[18rem] flex-col overflow-hidden float-surface"
          data-float="3"
          data-testid={`${testId}-panel`}
        >
          {panel}
        </div>
      )}
    </div>
  )
}
