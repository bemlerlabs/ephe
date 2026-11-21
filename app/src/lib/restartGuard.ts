/**
 * The gate in front of a restart.
 *
 * A relaunch ends the process the user is working in. Two conditions can be
 * worth more than the new bundle: a turn that is still running, and a message
 * the user typed but has not sent. The guard names both, and the update
 * surface shows which one is holding the restart back, so the button never
 * throws work away.
 *
 * The composer publishes its draft through the subscription store below.
 * `lib/panelEvents` carries a signal between panels the same way, and the guard
 * needs a value the chat store does not own.
 */
import { useSyncExternalStore } from 'react'
import { useChatStore } from '@/store/chatStore'

export type RestartBlock = 'running' | 'draft'

export interface RestartGuard {
  blocked: boolean
  reason: RestartBlock | null
}

let draft = ''
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

/** The composer publishes here; the cleared composer publishes an empty string. */
export function setComposerDraft(next: string): void {
  if (next === draft) return
  draft = next
  emit()
}

export function getComposerDraft(): string {
  return draft
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useComposerDraft(): string {
  return useSyncExternalStore(subscribe, getComposerDraft, () => '')
}

/** The rule as one read, for a caller that runs outside a render. */
export function restartGuardNow(): RestartGuard {
  if (useChatStore.getState().isTyping) return { blocked: true, reason: 'running' }
  if (draft.trim().length > 0) return { blocked: true, reason: 'draft' }
  return { blocked: false, reason: null }
}

/** The same rule as a subscription, for the surface that draws it. */
export function useRestartGuard(): RestartGuard {
  const running = useChatStore((s) => s.isTyping)
  const current = useComposerDraft()
  if (running) return { blocked: true, reason: 'running' }
  if (current.trim().length > 0) return { blocked: true, reason: 'draft' }
  return { blocked: false, reason: null }
}

/** The slice of the shell bridge this module reaches for. */
interface TauriProcessBridge {
  core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
  process?: { relaunch?: () => Promise<void> }
}

/**
 * Ask the shell to restart.
 *
 * The call goes through `window.__TAURI__.process.relaunch()`, the global the
 * process plugin defines while the app runs with `withGlobalTauri`. The same
 * command is reachable on the core channel, which is the second attempt, so a
 * build that wires the plugin without the global shim still restarts. Answers
 * false where no shell listens.
 */
export async function relaunchApp(): Promise<boolean> {
  const bridge = (window as unknown as { __TAURI__?: TauriProcessBridge }).__TAURI__
  const invoke = bridge?.core?.invoke
  // The shell's Python process loaded its code at start. It must not survive the
  // relaunch and answer for the version that is about to run.
  if (typeof invoke === 'function') {
    try {
      await invoke('stop_backend')
    } catch {
      /* an older shell has no such command; the restart is still the user's ask */
    }
  }
  const globalRelaunch = bridge?.process?.relaunch
  if (typeof globalRelaunch === 'function') {
    await globalRelaunch()
    return true
  }
  if (typeof invoke === 'function') {
    await invoke('plugin:process|restart')
    return true
  }
  return false
}
