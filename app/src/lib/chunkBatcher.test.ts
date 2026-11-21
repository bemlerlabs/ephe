import { describe, it, expect, vi } from 'vitest'
import { createChunkBatcher } from './chunkBatcher'

/** Fake rAF: callbacks are fired by hand (jsdom has no real frame scheduling). */
function fakeRaf() {
  const queue: Array<() => void> = []
  let id = 0
  return {
    raf: (cb: () => void) => {
      id++
      queue.push(cb)
      return id
    },
    cancelRaf: (rid: number) => {
      const idx = rid - 1
      if (idx >= 0 && idx < queue.length) queue.splice(idx, 1)
    },
    fire: () => {
      const cbs = queue.splice(0)
      cbs.forEach((cb) => cb())
    },
  }
}

describe('createChunkBatcher (D2 rAF-Batching)', () => {
  it('bundles several chunks per frame into one flush, keeping the order', () => {
    const flushes: string[] = []
    const fake = fakeRaf()
    const b = createChunkBatcher({
      onFlush: (text) => flushes.push(text),
      raf: fake.raf,
      cancelRaf: fake.cancelRaf,
    })

    b.add('Hal')
    b.add('lo')
    b.add(' Welt') // 3 chunks before the frame

    expect(flushes).toEqual([]) // no frame fired yet

    fake.fire() // 1 frame

    expect(flushes).toEqual(['Hallo Welt']) // EXACTLY 1 call, FIFO order
  })

  it('flush() returns the whole buffer synchronously (before done)', () => {
    const flushes: string[] = []
    const fake = fakeRaf()
    const b = createChunkBatcher({
      onFlush: (text) => flushes.push(text),
      raf: fake.raf,
      cancelRaf: fake.cancelRaf,
    })

    b.add('a')
    b.add('b')
    b.flush()
    expect(flushes).toEqual(['ab'])

    // a double flush after the synchronous flush must never appear:
    fake.fire()
    expect(flushes).toEqual(['ab'])
  })

  it('flush() on an empty buffer never calls onFlush', () => {
    const onFlush = vi.fn()
    const b = createChunkBatcher({ onFlush })
    b.flush()
    expect(onFlush).not.toHaveBeenCalled()
  })

  it('cancel() discards the buffer (abort/unmount)', () => {
    const onFlush = vi.fn()
    const fake = fakeRaf()
    const b = createChunkBatcher({
      onFlush,
      raf: fake.raf,
      cancelRaf: fake.cancelRaf,
    })
    b.add('teurer Text')
    b.cancel()
    fake.fire()
    b.flush()
    expect(onFlush).not.toHaveBeenCalled()
  })

  it('empty chunks are ignored (no empty flush)', () => {
    const onFlush = vi.fn()
    const fake = fakeRaf()
    const b = createChunkBatcher({
      onFlush,
      raf: fake.raf,
      cancelRaf: fake.cancelRaf,
    })
    b.add('')
    fake.fire()
    expect(onFlush).not.toHaveBeenCalled()
  })

  it('several frames in a row give one flush per frame', () => {
    const flushes: string[] = []
    const fake = fakeRaf()
    const b = createChunkBatcher({
      onFlush: (t) => flushes.push(t),
      raf: fake.raf,
      cancelRaf: fake.cancelRaf,
    })
    b.add('1')
    fake.fire()
    b.add('2')
    fake.fire()
    expect(flushes).toEqual(['1', '2'])
  })
})
