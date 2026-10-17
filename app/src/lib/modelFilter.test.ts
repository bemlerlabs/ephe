import { describe, it, expect } from 'vitest'
import { isJunkModel } from './modelFilter'

describe('isJunkModel (F-J, t5-Audit 2026-10-01)', () => {
  it('nackte "test"-Einträge sind Müll', () => {
    expect(isJunkModel('test')).toBe(true)
    expect(isJunkModel('Test')).toBe(true)
  })

  it('Embedding-Modelle sind Müll', () => {
    expect(isJunkModel('nomic-embed-text')).toBe(true)
    expect(isJunkModel('text-embedding-3-small')).toBe(true)
    expect(isJunkModel('bge-embed')).toBe(true)
  })

  it('normale Chat-Modelle bleiben stehen', () => {
    expect(isJunkModel('big-pickle')).toBe(false)
    expect(isJunkModel('gemma4:12b')).toBe(false)
    expect(isJunkModel('mimo-v2.5-free')).toBe(false)
    expect(isJunkModel(undefined)).toBe(false)
    expect(isJunkModel('')).toBe(false)
  })
})
