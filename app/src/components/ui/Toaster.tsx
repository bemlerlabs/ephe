import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle, Info, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { subscribeToast, type ToastItem } from '@/lib/toast'
import { PANEL_STATE_EVENT } from '@/lib/panelEvents'

const AUTO_DISMISS_MS = 5000
const ERROR_DISMISS_MS = 8000
const MAX_VISIBLE = 4

/**
 * The right-hand clearance. The panel is a fixed column at the window's right edge and its
 * tab bar sits at the very top of that edge — the same corner the stack occupies, so a toast
 * covered the controls the reader needs next (seen in every capture of the right column,
 * 2026-11-02: "60 messages restored from earlier sessions" printed straight over the tab
 * row). The panel already broadcasts its width and dock on every change for the content
 * column's padding; the stack reads the same fact and steps aside.
 */
function useRightClearance(): string | undefined {
  const [panel, setPanel] = useState<{ width: number; dock: string } | null>(null)
  useEffect(() => {
    const onState = (e: Event) => {
      const detail = (e as CustomEvent).detail as { open?: boolean; width?: number; dock?: string }
      if (!detail?.open || detail.dock !== 'right' || typeof detail.width !== 'number') {
        setPanel(null)
        return
      }
      setPanel({ width: detail.width, dock: detail.dock })
    }
    window.addEventListener(PANEL_STATE_EVENT, onState)
    return () => window.removeEventListener(PANEL_STATE_EVENT, onState)
  }, [])
  if (!panel) return undefined
  // The panel itself clamps to `min(width, 95vw)`; the stack answers for that clamp so a
  // wide panel on a narrow window cannot push the toast off the left edge.
  const taken = Math.min(panel.width, Math.round(window.innerWidth * 0.95))
  return `${taken + 16}px`
}

/**
 * G4 — global toaster (mounted once in App/Main).
 *
 * Subscribes to the toastBus, renders up to MAX_VISIBLE toasts
 * bottom-right, auto-dismiss (errors stay longer).
 *
 * Announcements come from two live regions that are mounted for the life of the
 * app, not from the toast rows: a region that is inserted together with its text
 * may never be announced, because the accessibility tree only reports a change
 * when the region was already there. The rows keep the text and the dismiss
 * button for reading and for the pointer; they carry no live semantics, so a
 * single message is not spoken twice.
 *
 * Where the stack sits: on a phone it hangs under the header; on a wide window it
 * keeps the top-right corner, under the chat's own top bar. The phone case is a
 * measured fix — the restore toast measured [16,720,358x44] at 390x844 while the
 * composer's bottom row sits at y=739, so the stack covered the model chip and the
 * send button (25px of overlap, 2026-10-13). A bottom offset cannot be made safe
 * there: the composer's height is not a constant (the textarea grows to max-h-32,
 * attachments wrap, and a h-16 buffer sits above it), so any "above the composer"
 * offset is stale the moment the composer grows. The band under the header is
 * always free instead, and the header measures a flat 53px below lg — the offset
 * below clears it. On a wide window the same rule applies to the bottom: the
 * composer is tall and grows, so the stack anchors top-right there too.
 */
export function Toaster() {
  const { t } = useTranslation()
  const [items, setItems] = useState<ToastItem[]>([])
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const right = useRightClearance()

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
      if (previous !== undefined) {
        clearTimeout(previous)
        timersRef.current.delete(item.id)
      }
      // A waiting update has no clock: it stays until the reader reloads or closes it.
      if (!item.sticky) {
        const tm = setTimeout(
          () => removeItem(item.id),
          item.kind === 'error' ? ERROR_DISMISS_MS : AUTO_DISMISS_MS,
        )
        timersRef.current.set(item.id, tm)
      }
    })
    return () => {
      unsub()
      timersRef.current.forEach((tm) => clearTimeout(tm))
      timersRef.current.clear()
    }
  }, [removeItem])

  // The newest message of each tone is what the standing regions carry. Deriving
  // it from the rows keeps a dismissed toast from leaving stale text behind.
  const announcement = (kind: 'error' | 'other') => {
    const item = [...items]
      .reverse()
      .find((x) => (kind === 'error' ? x.kind === 'error' : x.kind !== 'error'))
    if (!item) return ''
    return item.description ? `${item.title}. ${item.description}` : item.title
  }
  const polite = announcement('other')
  const assertive = announcement('error')

  return (
    <div
      role="region"
      aria-label={t('toast.region')}
      data-inert-exempt=""
      data-testid="toaster-region"
    >
      {/* Mounted from the first paint, so the change that follows is a change. */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        data-testid="toaster-live"
        className="sr-only"
      >
        {polite}
      </div>
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        data-testid="toaster-live-alert"
        className="sr-only"
      >
        {assertive}
      </div>
      {items.length > 0 && (
        <div
          data-testid="toaster-rail"
          data-cleared={right ? 'true' : 'false'}
          // The clearance is a custom property, so the phone rule keeps its centring: only
          // the wide layout reads a right offset, and below lg the rail stays where the
          // composer measurement put it.
          style={{ ['--toast-right']: right ?? '1rem' } as React.CSSProperties}
          className="fixed z-modal flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))] max-lg:left-1/2 max-lg:-translate-x-1/2 max-lg:top-[calc(env(safe-area-inset-top)+4rem)] lg:right-[var(--toast-right)] lg:top-[calc(env(safe-area-inset-top)+3.75rem)]"
        >
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
                className="float-surface p-3 flex items-start gap-2.5 text-ui-sm"
                data-float="3"
              >
                <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${iconColor}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-foreground/90 leading-tight">{item.title}</p>
                  {item.description && (
                    <p className="text-ink-faint text-ui-xs mt-0.5 leading-tight">
                      {item.description}
                    </p>
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
                  onClick={() => {
                    item.onDismiss?.()
                    removeItem(item.id)
                  }}
                  aria-label={t('toast.close')}
                  className="inline-flex items-center justify-center shrink-0 min-h-6 min-w-6 text-ink-faint hover:text-foreground/70 transition-colors pointer-coarse:min-h-11 pointer-coarse:min-w-11"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
