/**
 * G4 — the toast bus (context-free, reachable from any module).
 *
 * toastBus.info/success/error: show a toast.
 * toastBus.subscribe: register a listener; returns the unsubscribe function.
 *
 * The Toaster (components/ui/Toaster.tsx) is the only subscriber in the app
 * code — every other place calls toastBus.info/success/error.
 * `toast` is an alias pointing at the same shortcuts (convenience).
 */
export type ToastKind = 'info' | 'success' | 'error'

/** Optional action button inside the toast (e.g. a "Neu laden" reload action on a service-worker update). <!-- language-gate: ignore (quotes the German product label the UI renders) --> */
export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastItem {
  id: string
  kind: ToastKind
  title: string
  description?: string
  action?: ToastAction
}

type Listener = (item: ToastItem) => void

const listeners = new Set<Listener>()

function broadcast(
  kind: ToastKind,
  title: string,
  description?: string,
  action?: ToastAction,
): void {
  const item: ToastItem = { id: crypto.randomUUID(), kind, title, description, action }
  listeners.forEach((l) => l(item))
}

export const toastBus = {
  info: (title: string, description?: string, action?: ToastAction) =>
    broadcast('info', title, description, action),
  success: (title: string, description?: string, action?: ToastAction) =>
    broadcast('success', title, description, action),
  error: (title: string, description?: string, action?: ToastAction) =>
    broadcast('error', title, description, action),
  subscribe: (l: Listener): (() => void) => {
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  },
}

/** Alias for the shortcut methods (toast.info/success/error). */
export const toast = toastBus

/** Standalone functions (for imports like `import { subscribeToast }`). */
export const subscribeToast = toastBus.subscribe
