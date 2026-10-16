import { describe, it, expect } from 'vitest'
import { ComposerHistory } from '@/lib/composerHistory'

describe('ComposerHistory recall', () => {
  it('recalls the most recent message first with ↑', () => {
    const h = new ComposerHistory()
    h.add('erste')
    h.add('zweite')
    expect(h.prev()).toBe('zweite')
    expect(h.prev()).toBe('erste')
    expect(h.prev()).toBe('erste') // at the start: stays on 'erste' // language-gate: ignore (names the asserted sample-message fixture)
  })

  it('returns null for ↑ on empty history', () => {
    const h = new ComposerHistory()
    expect(h.prev()).toBeNull()
    expect(h.next()).toBeNull()
  })

  it('cycles back to neutral with ↓ at the end', () => {
    const h = new ComposerHistory()
    h.add('eins')
    h.add('zwei')
    h.prev() // returns 'zwei' // language-gate: ignore (names the asserted sample-message fixture)
    h.next() // returns 'eins' // language-gate: ignore (names the asserted sample-message fixture)
    expect(h.next()).toBeNull() // neutral
  })

  it('returns the saved draft after cycling past the end', () => {
    const h = new ComposerHistory()
    h.add('eins')
    h.setDraft('mein Entwurf')
    // first prev from neutral → the last message
    h.prev()
    expect(h.next()).toBe('mein Entwurf')
  })

  it('dedupes consecutive identical messages', () => {
    const h = new ComposerHistory()
    h.add('a')
    h.add('a')
    expect(h.index().total).toBe(1)
  })

  it('ignores empty sends', () => {
    const h = new ComposerHistory()
    h.add('   ')
    h.add('')
    expect(h.index().total).toBe(0)
  })

  it('reports position for display', () => {
    const h = new ComposerHistory()
    h.add('eins')
    h.add('zwei')
    h.prev() // lands on 'zwei' // language-gate: ignore (names the asserted sample-message fixture)
    expect(h.index()).toEqual({ pos: 2, total: 2 })
    h.reset()
    expect(h.index()).toEqual({ pos: 0, total: 2 })
  })

  it('resets cursor on add after a send', () => {
    const h = new ComposerHistory()
    h.add('eins')
    h.prev() // lands on 'eins' // language-gate: ignore (names the asserted sample-message fixture)
    h.add('zwei')
    expect(h.index()).toEqual({ pos: 0, total: 2 })
    expect(h.prev()).toBe('zwei')
  })
})

describe('ComposerHistory queue editing', () => {
  it('enqueues and dequeues in order', () => {
    const h = new ComposerHistory()
    h.enqueue('a')
    h.enqueue('b')
    expect(h.queueCount()).toBe(2)
    expect(h.dequeue()?.text).toBe('a')
    expect(h.dequeue()?.text).toBe('b')
    expect(h.dequeue()).toBeNull()
    expect(h.queueCount()).toBe(0)
  })

  it('ignores empty queue inserts', () => {
    const h = new ComposerHistory()
    h.enqueue('   ')
    expect(h.queueCount()).toBe(0)
  })

  it('clears the queue', () => {
    const h = new ComposerHistory()
    h.enqueue('a')
    h.clearQueue()
    expect(h.queueCount()).toBe(0)
  })

  it('preserves attachments in queue entries', () => {
    const h = new ComposerHistory()
    h.enqueue('a', [{ path: '/tmp/x', name: 'x' }])
    const entry = h.dequeue()
    expect(entry?.attachments).toEqual([{ path: '/tmp/x', name: 'x' }])
  })
})
