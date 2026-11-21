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
  /** A toast that waits for the reader — a new version on disk — gets no clock. */
  sticky?: boolean
  /** Runs when the reader closes the toast themselves, never on the timeout. */
  onDismiss?: () => void
}

/** The two flags a caller may attach to any toast without changing its wording. */
export interface ToastFlags {
  sticky?: boolean
  onDismiss?: () => void
}

type Listener = (item: ToastItem) => void

const listeners = new Set<Listener>()

function broadcast(
  kind: ToastKind,
  title: string,
  description?: string,
  action?: ToastAction,
  id?: string,
  flags?: ToastFlags,
): void {
  const item: ToastItem = {
    id: id ?? crypto.randomUUID(),
    kind,
    title,
    description,
    action,
    ...(flags?.sticky ? { sticky: true } : {}),
    ...(flags?.onDismiss ? { onDismiss: flags.onDismiss } : {}),
  }
  listeners.forEach((l) => l(item))
}

export const toastBus = {
  /** A toast, or — with an `id` already on screen — the same toast with new text. */
  info: (
    title: string,
    description?: string,
    action?: ToastAction,
    id?: string,
    flags?: ToastFlags,
  ) => broadcast('info', title, description, action, id, flags),
  success: (
    title: string,
    description?: string,
    action?: ToastAction,
    id?: string,
    flags?: ToastFlags,
  ) => broadcast('success', title, description, action, id, flags),
  error: (
    title: string,
    description?: string,
    action?: ToastAction,
    id?: string,
    flags?: ToastFlags,
  ) => broadcast('error', title, description, action, id, flags),
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
