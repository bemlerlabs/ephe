/**
 * Ephe — checkpoints & rollback (P2-7)
 *
 * Snapshot system for sessions: a message list can be saved as a
 * checkpoint at any time and rolled back later by ID.
 *
 * Pure functions with no DOM or store dependency → easy to test.
 */

import type { ChatMessage } from '@/types'

export interface ChatCheckpoint {
  id: string
  label: string
  createdAt: number
  messages: ChatMessage[]
}

/** Creates a checkpoint snapshot (deep copy) of the messages. */
export function createCheckpoint(messages: ChatMessage[], label = 'Checkpoint'): ChatCheckpoint {
  return {
    id: crypto.randomUUID(),
    label,
    createdAt: Date.now(),
    messages: messages.map((m) => ({ ...m })),
  }
}

/** Rolls a session back to the checkpoint state (deep copy). */
export function rollbackToCheckpoint(
  checkpointId: string,
  checkpoints: ChatCheckpoint[],
): ChatMessage[] | null {
  const cp = checkpoints.find((c) => c.id === checkpointId)
  if (!cp) return null
  return cp.messages.map((m) => ({ ...m }))
}

/** Checkpoints sorted descending by creation time (newest first). */
export function listCheckpoints(checkpoints: ChatCheckpoint[]): ChatCheckpoint[] {
  return [...checkpoints].sort((a, b) => b.createdAt - a.createdAt)
}

/** Removes a checkpoint. */
export function deleteCheckpoint(
  checkpoints: ChatCheckpoint[],
  checkpointId: string,
): ChatCheckpoint[] {
  return checkpoints.filter((c) => c.id !== checkpointId)
}
