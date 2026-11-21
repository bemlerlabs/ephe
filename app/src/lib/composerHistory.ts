/**
 * Ephe — Composer History (P2-6)
 *
 * Terminal-like recall history for the composer:
 *  - ↑/↓ pages through messages that were already sent
 *  - queue editing: several messages can be prepared in advance
 *    (Enter sends the current one; Alt+Enter or the like puts it into the queue)
 *
 * Plain class without any DOM dependency → easy to test.
 */

export interface QueueEntry {
  text: string
  attachments?: unknown[]
}

export class ComposerHistory {
  private entries: string[] = []
  private cursor = -1 // -1 = neutral (empty composer)
  private queue: QueueEntry[] = []
  private draft = ''

  /** Add a newly sent message to the history (dedup: no direct duplicates). */
  add(text: string): void {
    const trimmed = text.trim()
    if (!trimmed) return
    if (this.entries[this.entries.length - 1] !== trimmed) {
      this.entries.push(trimmed)
    }
    // After sending: reset the cursor to neutral
    this.cursor = -1
    this.draft = ''
  }

  /** ↑ — older message; returns the message, or null at the beginning. */
  prev(): string | null {
    if (this.entries.length === 0) return null
    this.cursor = this.cursor === -1 ? this.entries.length - 1 : Math.max(0, this.cursor - 1)
    return this.entries[this.cursor] ?? null
  }

  /** ↓ — newer message; null once at the end (neutral). */
  next(): string | null {
    if (this.cursor === -1) return null
    this.cursor += 1
    if (this.cursor >= this.entries.length) {
      this.cursor = -1
      return this.draft || null
    }
    return this.entries[this.cursor] ?? null
  }

  /** Current history index (for the "3/5" display). */
  index(): { pos: number; total: number } {
    const total = this.entries.length
    const pos = this.cursor === -1 ? 0 : this.cursor + 1
    return { pos, total }
  }

  /** Set the cursor back to neutral (Escape). */
  reset(): void {
    this.cursor = -1
    this.draft = ''
  }

  /** Set the draft (current composer content, the baseline for recall). */
  setDraft(text: string): void {
    this.draft = text
  }

  /** Put the current message into the queue (queue editing). */
  enqueue(text: string, attachments?: unknown[]): void {
    if (text.trim()) {
      this.queue.push({ text: text.trim(), attachments })
    }
  }

  /** Take the next queued message; null when the queue is empty. */
  dequeue(): QueueEntry | null {
    if (this.queue.length === 0) return null
    return this.queue.shift()!
  }

  /** Queue contents (for the "2 in Queue" display). */
  queueCount(): number {
    return this.queue.length
  }

  /** Empty the queue. */
  clearQueue(): void {
    this.queue = []
  }
}
