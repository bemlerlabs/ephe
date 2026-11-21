/**
 * The artifact card reader. A server that names what a file is sends `label_code`
 * (core/artifact_markers.py owns the names), and this picks the reader's own language
 * for it; an unknown code or a bundle without the entry keeps the server's sentence,
 * so a missing translation costs a language and never the card.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { exists, t } = vi.hoisted(() => ({ exists: vi.fn(), t: vi.fn() }))
vi.mock('@/i18n', () => ({ default: { exists, t } }))

import { artifactLabel, artifactName } from './artifactLabel'
import en from '@/locales/en.json'
import de from '@/locales/de.json'

describe('artifactLabel', () => {
  beforeEach(() => {
    exists.mockReset()
    t.mockReset()
  })

  it('returns the fallback when the server sent no code', () => {
    expect(artifactLabel(undefined, { name: 'a.wav' }, '📄 PDF: a.pdf')).toBe('📄 PDF: a.pdf')
    expect(exists).not.toHaveBeenCalled()
  })

  it('returns the fallback when the bundle has no leaf for the code', () => {
    exists.mockReturnValue(false)
    expect(artifactLabel('audioHologram', { name: 'a.wav' }, '🔊 Voice: a.wav')).toBe(
      '🔊 Voice: a.wav',
    )
  })

  it('reads a known code from the bundle with the file name', () => {
    exists.mockReturnValue(true)
    t.mockReturnValue('resolved from the active bundle')
    expect(artifactLabel('audioMusicBed', { name: 'calm.wav' }, '🎵 Music bed: calm.wav')).toBe(
      'resolved from the active bundle',
    )
    expect(exists).toHaveBeenCalledWith('artifactLabel.audioMusicBed')
    expect(t).toHaveBeenCalledWith('artifactLabel.audioMusicBed', {
      name: 'calm.wav',
      defaultValue: '🎵 Music bed: calm.wav',
    })
  })

  it('names the file by its last path segment', () => {
    expect(artifactName('/Users/me/artifacts/calm.wav')).toBe('calm.wav')
    expect(artifactName('calm.wav')).toBe('calm.wav')
    expect(artifactName('')).toBe('')
  })
})

describe('the audio roles in both bundles', () => {
  const codes = ['audioVoice', 'audioMusicBed', 'audioSoundEffect'] as const
  const bundles: Array<[string, typeof en]> = [
    ['en', en],
    ['de', de as typeof en],
  ]

  it('names each role differently in each language', () => {
    for (const [language, bundle] of bundles) {
      const cards = bundle.artifactLabel
      const words = codes.map((code) => cards[code].split(':')[0])
      expect(new Set(words).size, language).toBe(codes.length)
      expect(new Set(codes.map((code) => cards[code])).size, language).toBe(codes.length)
    }
  })

  it('carries the file name in every card', () => {
    for (const [language, bundle] of bundles) {
      const cards = bundle.artifactLabel
      for (const code of codes) expect(cards[code], language).toContain('{{name}}')
    }
  })
})
