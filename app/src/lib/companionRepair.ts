/**
 * QD-005B — the one fact the setup screen owns and the companion reads.
 *
 * The repair card is drawn on the setup route; the companion lives in the chat.
 * A wrong key binding does not stop being true because the screen that names it
 * was left, so the producer announces the state and not the mount: the setup
 * page says true when it renders the card, false when the user dismisses or
 * fixes it. No DOM polling, no second status request.
 */
import { useSyncExternalStore } from 'react'

let repairVisible = false
const listeners = new Set<() => void>()

export function announceSetupRepair(visible: boolean): void {
  if (visible === repairVisible) return
  repairVisible = visible
  for (const listener of listeners) listener()
}

export function setupRepairSnapshot(): boolean {
  return repairVisible
}

export function subscribeSetupRepair(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useSetupRepair(): boolean {
  return useSyncExternalStore(subscribeSetupRepair, setupRepairSnapshot, setupRepairSnapshot)
}
