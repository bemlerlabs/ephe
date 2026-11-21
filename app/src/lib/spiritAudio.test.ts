// The companion's voice has three doors, and one of them is not a sound control:
// `appearance.animations_enabled` mutes the synthesizer too, because a person who
// asked for no motion did not ask to be accompanied by chimes. The register row for
// that switch names the consequence, so the gate is pinned at the function that
// decides it (`core` of the audio path: every play call passes through here).
import { describe, expect, it, beforeEach, vi } from 'vitest'

import { seedDeepSettings } from './deepSettings'
import { spiritAudioAllowed } from './spiritAudio'
import type { DeepSection } from '@/types'

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ provider: { type: 'local_ollama', model: 'x' }, deep: [] })),
}))

function boolField(key: string, value: boolean): DeepSection['fields'][number] {
  return { key, type: 'bool', label: key, labelEn: key, default: value, value }
}

function seedSwitches({ sound = true, animations = true } = {}): void {
  seedDeepSettings([
    {
      key: 'appearance',
      fields: [
        boolField('appearance.companion_sound', sound),
        boolField('appearance.animations_enabled', animations),
      ],
    },
  ])
}

function systemPrefersReducedMotion(matches: boolean): void {
  window.matchMedia = vi.fn(() => ({
    matches,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
}

beforeEach(() => {
  seedDeepSettings(null)
  vi.restoreAllMocks()
})

describe('the three doors of the companion sound', () => {
  it('plays when the person keeps sound, keeps animations and asks for no reduced motion', () => {
    seedSwitches()
    systemPrefersReducedMotion(false)
    expect(spiritAudioAllowed()).toBe(true)
  })

  it('is silent when the sound switch is off', () => {
    seedSwitches({ sound: false })
    systemPrefersReducedMotion(false)
    expect(spiritAudioAllowed()).toBe(false)
  })

  it('is silent when the animations switch is off, whatever the sound switch says', () => {
    seedSwitches({ sound: true, animations: false })
    systemPrefersReducedMotion(false)
    expect(spiritAudioAllowed()).toBe(false)
  })

  it('is silent when the system asks for reduced motion', () => {
    seedSwitches()
    systemPrefersReducedMotion(true)
    expect(spiritAudioAllowed()).toBe(false)
  })

  it('keeps playing when the system reports no matchMedia at all', () => {
    seedSwitches()
    delete (window as { matchMedia?: typeof window.matchMedia }).matchMedia
    expect(spiritAudioAllowed()).toBe(true)
  })
})
