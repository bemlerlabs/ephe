/**
 * Command shapes the user taught the co-pilot, kept on this device.
 *
 * The safe list in `companionCopilot` holds the commands we can defend on our
 * own; everything else is refused. This store is the one exception the owner
 * asked for: after a refusal the user may say "this shape is fine", and that
 * decision is remembered per verb. A forbidden marker can never enter — it is
 * checked when the shape is stored and again on every use, so remembering
 * `grep` does not make `grep > out.txt` safe.
 */
import { useSyncExternalStore } from 'react'
import { isShellForbidden, shellVerb } from './companionCopilot'

const KEY = 'ephe.companion.rememberedShapes'
const EMPTY: readonly string[] = []

const listeners = new Set<() => void>()
let verbs: readonly string[] = read()

function read(): readonly string[] {
  try {
    const raw = window.localStorage.getItem(KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.filter((entry) => typeof entry === 'string' && entry) : EMPTY
  } catch {
    return EMPTY
  }
}

function write(next: readonly string[]) {
  verbs = next
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // A webview that refuses storage still keeps the in-memory list for the session.
  }
  for (const listener of listeners) listener()
}

export function rememberedShellVerbs(): readonly string[] {
  return verbs
}

export function subscribeRemembered(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** A plain verb with no fail-closed marker anywhere in the command line. */
export function canRememberShape(command: string): boolean {
  return Boolean(shellVerb(command)) && !isShellForbidden(command)
}

export function rememberShellShape(command: string): boolean {
  if (!canRememberShape(command)) return false
  const verb = shellVerb(command) ?? ''
  if (!verbs.includes(verb)) write([...verbs, verb])
  return true
}

export function forgetShellShapes(): void {
  write(EMPTY)
}

export function useRememberedShellVerbs(): readonly string[] {
  return useSyncExternalStore(subscribeRemembered, rememberedShellVerbs, () => EMPTY)
}
