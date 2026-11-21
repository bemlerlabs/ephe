import { describe, expect, it } from 'vitest'
import { companionMood } from './companionState'

describe('companionMood', () => {
  it('maps the one run state to the actor behavior', () => {
    expect(companionMood('ready')).toBe('rest')
    expect(companionMood('working')).toBe('moving')
    expect(companionMood('waiting')).toBe('still')
    expect(companionMood('done')).toBe('settle')
  })
})
