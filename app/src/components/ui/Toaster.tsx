import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle, Info, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { subscribeToast, type ToastItem } from '@/lib/toast'

const AUTO_DISMISS_MS = 5000
const ERROR_DISMISS_MS = 8000
const MAX_VISIBLE = 4

/**
 * G4 — global toaster (mounted once in App/Main).
 *
 * Subscribes to the toastBus, renders up to MAX_VISIBLE toasts
 * bottom-right, auto-dismiss (errors stay longer). a11y: each toast
 * role="status" + aria-live (error: assertive).
 *
 * Where the stack sits: on a phone it hangs under the header, on a wide window it
 * keeps the bottom-left corner. The phone case is a measured fix — the restore
 * toast measured [16,720,358x44] at 390x844 while the composer's bottom row sits
 * at y=739, so the stack covered the model chip and the send button (25px of
 * overlap, 2026-10-13). A bottom offset cannot be made safe there: the composer's
 * height is not a constant (the textarea grows to max-h-32, attachments wrap, and
 * a h-16 buffer sits above it), so any "above the composer" offset is stale the
 * moment the composer grows. The band under the header is always free instead,
 * and the header measures a flat 53px below lg — the offset below clears it.
 */
export function Toaster() {
  const { t } = useTranslation()
  const [items, setItems] = useState<ToastItem[]>([])
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((x) => x.id !== id))
    const tm = timersRef.current.get(id)
    if (tm !== undefined) {
      clearTimeout(tm)
      timersRef.current.delete(id)
    }
  }, [])

  useEffect(() => {
    const unsub = subscribeToast((item) => {
      setItems((prev) => {
        const at = prev.findIndex((x) => x.id === item.id)
        if (at >= 0) {
          const next = [...prev]
          next[at] = item
          return next
        }
        return [...prev, item].slice(-MAX_VISIBLE)
      })
      // A re-used id replaces the toast and restarts its clock: one restore, one row.
      const previous = timersRef.current.get(item.id)
      if (previous !== undefined) clearTimeout(previous)
      const tm = setTimeout(
        () => removeItem(item.id),
        item.kind === 'error' ? ERROR_DISMISS_MS : AUTO_DISMISS_MS,
      )
      timersRef.current.set(item.id, tm)
    })
    return () => {
      unsub()
      timersRef.current.forEach((tm) => clearTimeout(tm))
      timersRef.current.clear()
    }
  }, [removeItem])

  if (items.length === 0) return null

  return (
    <div className="fixed z-modal flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))] left-1/2 -translate-x-1/2 max-lg:top-[calc(env(safe-area-inset-top)+4rem)] lg:bottom-20">
      {items.map((item) => {
        const Icon =
          item.kind === 'error' ? AlertTriangle : item.kind === 'success' ? CheckCircle : Info
        const iconColor =
          item.kind === 'error'
            ? 'text-status-danger'
            : item.kind === 'success'
              ? 'text-status-success'
              : 'text-foreground/60'
        return (
          <div
            key={item.id}
            role="status"
            aria-live={item.kind === 'error' ? 'assertive' : 'polite'}
            className="float-surface p-3 flex items-start gap-2.5 text-ui-sm"
            data-float="3"
          >
            <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${iconColor}`} />
            <div className="flex-1 min-w-0">
              <p className="text-foreground/90 leading-tight">{item.title}</p>
              {item.description && (
                <p className="text-ink-faint text-ui-xs mt-0.5 leading-tight">{item.description}</p>
              )}
              {item.action && (
                <button
                  onClick={() => {
                    item.action?.onClick()
                    removeItem(item.id)
                  }}
                  className="mt-2 text-ui-xs font-medium text-brand hover:text-brand transition-colors"
                >
                  {item.action.label}
                </button>
              )}
            </div>
            <button
              onClick={() => removeItem(item.id)}
              aria-label={t('toast.close')}
              className="inline-flex items-center justify-center shrink-0 min-h-6 min-w-6 text-ink-faint hover:text-foreground/70 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
