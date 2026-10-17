/**
 * Chunk batcher (PWA chat UX plan, Task D2 — rAF batching).
 *
 * Problem: while streaming the backend sends several `chunk` events per frame
 * (Ollama/vLLM: typically 5–20 chunks/frame). One chunk per call would trigger
 * appendChunk → store-set → React render — i.e. 5–20
 * full re-render cycles per frame for the very same visible
 * appended text.
 *
 * Solution: chunks accumulate in a buffer and are handed to the store
 * EXACTLY ONCE per requestAnimationFrame window via onFlush(text)
 * (1 appendChunk → 1 set → 1 render).
 *
 * Guaranteed:
 *  - order is preserved (FIFO buffer)
 *  - flush() returns the whole buffer synchronously (empty → no call)
 *  - cancel() drops the buffer (abort/unmount)
 *
 * Testable: raf/cancel-RaF are injectable (jsdom has no real
 * frame scheduling — tests drive a fake RaF).
 */
export interface ChunkBatcher {
  /** Append a chunk and (if needed) schedule the rAF flush. */
  add: (chunk: string) => void
  /** Empty the buffer immediately and synchronously (before done/abort/unmount). */
  flush: () => void
  /** Discard the buffer + cancel the scheduled rAF (abort). */
  cancel: () => void
}

export interface ChunkBatcherOptions {
  /** Called with the complete accumulated text (only when non-empty). */
  onFlush: (text: string) => void
  /** requestAnimationFrame implementation (default: window.requestAnimationFrame). */
  raf?: (cb: () => void) => number
  /** cancelAnimationFrame implementation (default: window.cancelAnimationFrame). */
  cancelRaf?: (id: number) => void
}

export function createChunkBatcher(opts: ChunkBatcherOptions): ChunkBatcher {
  const raf =
    opts.raf ??
    ((cb: () => void) =>
      typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame(cb)
        : (setTimeout(cb, 16) as unknown as number))
  const cancelRaf =
    opts.cancelRaf ??
    ((id: number) => {
      if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(id)
      else clearTimeout(id)
    })

  let buffer = ''
  let scheduled = false
  let rafId = 0

  return {
    add: (chunk: string) => {
      if (!chunk) return
      buffer += chunk
      if (scheduled) return
      scheduled = true
      rafId = raf(() => {
        scheduled = false
        const text = buffer
        buffer = ''
        if (text) opts.onFlush(text)
      })
    },
    flush: () => {
      // Cancel the pending rAF first (otherwise a double flush)
      if (scheduled) {
        cancelRaf(rafId)
        scheduled = false
      }
      const text = buffer
      buffer = ''
      if (text) opts.onFlush(text)
    },
    cancel: () => {
      if (scheduled) {
        cancelRaf(rafId)
        scheduled = false
      }
      buffer = ''
    },
  }
}
