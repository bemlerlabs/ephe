import { describe, it, expect } from 'vitest'
import { claimsMissingImage } from './artifactClaims'
import type { ProducedFile } from '@/components/dashboard/artifacts/messageCard'

const png: ProducedFile = { key: 'k', name: 'cat.png', path: '/tmp/cat.png', kind: 'png' }

describe('S17: an image claim without an image', () => {
  it('flags a past-tense image claim when the turn registered no image', () => {
    expect(claimsMissingImage('I generated an image of a cat.', [])).toBe(true)
    expect(claimsMissingImage('Ich habe ein Bild erstellt.', [])).toBe(true)
  })

  it('stays quiet when the turn registered an image', () => {
    expect(claimsMissingImage('I generated an image of a cat.', [png])).toBe(false)
  })

  it('stays quiet for a refusal and for unrelated wording', () => {
    expect(claimsMissingImage('I cannot generate an image here.', [])).toBe(false)
    expect(claimsMissingImage('The table was created from your data.', [])).toBe(false)
  })
})
