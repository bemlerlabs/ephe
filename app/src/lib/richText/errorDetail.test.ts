import { describe, it, expect } from 'vitest'
import { errorDetail } from './errorDetail'

describe('errorDetail', () => {
  it('collapses a multi-line renderer report into one line', () => {
    const err = new Error('Parse error on line 2:\n  A --> B\n     ^\nExpecting SEMI')
    expect(errorDetail(err)).toBe('Parse error on line 2: A --> B ^ Expecting SEMI')
  })

  it('reads the reason mermaid puts on a thrown object', () => {
    expect(errorDetail({ str: 'Cannot read properties of undefined' })).toBe(
      'Cannot read properties of undefined',
    )
  })

  it('accepts a bare string', () => {
    expect(errorDetail('boom')).toBe('boom')
  })

  it('truncates a wall of text instead of pasting it into the bubble', () => {
    const detail = errorDetail('x'.repeat(900))
    expect(detail).toHaveLength(240)
    expect(detail.endsWith('…')).toBe(true)
  })

  it('returns nothing for a value that carries no message', () => {
    expect(errorDetail(undefined)).toBe('')
  })
})
