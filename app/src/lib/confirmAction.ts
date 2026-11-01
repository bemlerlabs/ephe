/**
 * Ephe — the request side of one confirmation (finding #68).
 *
 * `window.confirm` prints our sentence and then lets the operating system name the button,
 * which answers "Delete this checkpoint?" with "OK". The verb belongs to the action, so the
 * question is handed to the shell's own sheet (`components/ui/ConfirmDialog`) and the caller
 * awaits the answer.
 *
 * The state lives here rather than in the component because the surfaces that ask are
 * models and hooks: a hook has to import a function, not a render tree.
 */

export interface ConfirmRequest {
  /** The question, with its consequence inside it when there is one. */
  title: string
  /** The verb the confirming button carries: "Delete checkpoint", never "OK". */
  action: string
  /** A refusal with its own word; `common.cancel` answers when it is absent. */
  cancel?: string
}

let mounted = false
let pending: ConfirmRequest | null = null
let settle: ((accepted: boolean) => void) | null = null
const subscribers = new Set<() => void>()

function emit() {
  for (const notify of subscribers) notify()
}

/** Ask the reader; true only arrives from the button carrying `request.action`. */
export function askConfirm(request: ConfirmRequest): Promise<boolean> {
  // Without a host the question has no surface. The native sheet is the fallback there:
  // swallowing the action would read as a broken control.
  if (!mounted) return Promise.resolve(window.confirm(request.title))
  if (settle) settle(false)
  pending = request
  return new Promise<boolean>((resolve) => {
    settle = resolve
    emit()
  })
}

/** The one answer path: a sheet closed without a press is a refusal. */
export function answerConfirm(accepted: boolean): void {
  const resolve = settle
  settle = null
  pending = null
  resolve?.(accepted)
  emit()
}

export function subscribeConfirm(notify: () => void): () => void {
  subscribers.add(notify)
  return () => subscribers.delete(notify)
}

export function pendingConfirm(): ConfirmRequest | null {
  return pending
}

/** The host announces itself; a request that outlives the host is answered as refused. */
export function registerConfirmHost(): () => void {
  mounted = true
  emit()
  return () => {
    mounted = false
    answerConfirm(false)
  }
}
