/**
 * Ephe — the one state of the task register (register #107).
 *
 * The register is the column that holds the tasks: the list, its filter, the two nav
 * tiers. It used to be a second permanent column beside the frame's rail, which made
 * the left edge two sidebars and put a second "New task" and a second "Search" next to
 * the places the rail already names. It is the body of the rail's Task row now, so the
 * choice of showing it belongs to the rail (in the frame) and the column that answers
 * it lives in the chat page — two components, one state, which is why it sits here
 * rather than in either of them.
 *
 * The value is the person's, not the session's: `ephe-sidebar-collapsed`, the key the
 * column carried before the fusion, is what the first read falls back to, so nobody
 * finds a column they had closed standing open again.
 */
import { useSyncExternalStore } from 'react'

const OPEN_KEY = 'ephe.register.open'
const LEGACY_COLLAPSED_KEY = 'ephe-sidebar-collapsed'

function seed(): boolean {
  const stored = localStorage.getItem(OPEN_KEY)
  if (stored === '0' || stored === '1') return stored === '1'
  return localStorage.getItem(LEGACY_COLLAPSED_KEY) !== '1'
}

let open = seed()
const listeners = new Set<() => void>()

export function registerOpen(): boolean {
  return open
}

export function setRegisterOpen(next: boolean): void {
  if (next === open) return
  open = next
  localStorage.setItem(OPEN_KEY, next ? '1' : '0')
  for (const listener of [...listeners]) listener()
}

export function toggleRegister(): void {
  setRegisterOpen(!open)
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The register's state, read by both components that can change it. */
export function useRegisterOpen(): boolean {
  return useSyncExternalStore(subscribe, registerOpen)
}
