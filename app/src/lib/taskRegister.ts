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
 * The value is the person's, not the session's, and it starts folded: the layout the old
 * key described (`ephe-sidebar-collapsed`, a column that was never fully away — 56 px of
 * icon stub beside the rail) is the thing this replaced, so reading it as a choice about
 * *this* layout would answer a question nobody was asked. A person who wants the list
 * open gets it with one click and is remembered from then on.
 */
import { useSyncExternalStore } from 'react'

const OPEN_KEY = 'ephe.register.open'

function seed(): boolean {
  return localStorage.getItem(OPEN_KEY) === '1'
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
