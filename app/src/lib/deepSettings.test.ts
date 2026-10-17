// I3-4: the client wiring — evaluate the register and apply Appearance on <html>.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'

import {
  UI_FONT_SIZE_BASE_PX,
  applyDeepAppearance,
  deepBool,
  deepNumber,
  deepSelect,
  deepText,
  deepValue,
  initDeepSettings,
  seedDeepSettings,
  subscribeDeepSettings,
  useDeepSelect,
} from './deepSettings'
import { getSettings } from '@/lib/api'
import type { DeepSection } from '@/types'

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ provider: { type: 'local_ollama', model: 'x' }, deep: [] })),
}))

function field(
  key: string,
  type: DeepSection['fields'][number]['type'],
  value: string | number | boolean | null,
  extra: Partial<DeepSection['fields'][number]> = {},
): DeepSection['fields'][number] {
  return {
    key,
    type,
    label: key,
    labelEn: key,
    default: value,
    value,
    ...extra,
  }
}

const sections: DeepSection[] = [
  {
    key: 'appearance',
    fields: [
      field('appearance.font_scale', 'number', 150, { min: 80, max: 150 }),
      field('appearance.animations_enabled', 'bool', false),
      field('appearance.show_timestamps', 'bool', true),
    ],
  },
]

beforeEach(() => {
  document.documentElement.style.removeProperty('--ui-font-size')
  document.documentElement.classList.remove('no-motion')
  seedDeepSettings(null)
})

describe('Zugriff ohne Register', () => {
  it('gibt den Fallback zurueck, statt zu werfen', () => {
    expect(deepBool('appearance.animations_enabled', true)).toBe(true)
    expect(deepNumber('appearance.font_scale', 100)).toBe(100)
    expect(deepSelect('appearance.skin', 'default')).toBe('default')
    expect(deepValue('appearance.compakt', 'x')).toBe('x')
  })
})

describe('seedDeepSettings', () => {
  it('nimmt Wert vor Default und laesst leeren Wert beim Default', () => {
    seedDeepSettings([
      {
        key: 'advanced',
        fields: [
          { ...field('advanced.api_timeout', 'number', 120), value: 300 },
          field('delegation.model', 'text', '', { value: null }),
        ],
      },
    ])
    expect(deepNumber('advanced.api_timeout', 0)).toBe(300)
    expect(deepText('delegation.model', 'leer')).toBe('')
  })

  it('meldet Hoerer nach jedem Seed', () => {
    const hear = vi.fn()
    const off = subscribeDeepSettings(hear)
    seedDeepSettings(sections)
    expect(hear).toHaveBeenCalled()
    off()
    hear.mockClear()
    seedDeepSettings(null)
    expect(hear).not.toHaveBeenCalled()
  })
})

describe('applyDeepAppearance', () => {
  it('skaliert die eine Typo-Stufe der App', () => {
    seedDeepSettings(sections)
    expect(document.documentElement.style.getPropertyValue('--ui-font-size')).toBe(
      `${UI_FONT_SIZE_BASE_PX * 1.5}px`,
    )
  })

  it('legt no-motion an, wenn Animationen aus sind', () => {
    seedDeepSettings(sections)
    expect(document.documentElement.classList.contains('no-motion')).toBe(true)
    seedDeepSettings([
      { key: 'appearance', fields: [field('appearance.animations_enabled', 'bool', true)] },
    ])
    expect(document.documentElement.classList.contains('no-motion')).toBe(false)
  })

  it('klemmt einen mutwilligen Schuppen in den Register-Bereich', () => {
    seedDeepSettings([
      { key: 'appearance', fields: [field('appearance.font_scale', 'number', 4000)] },
    ])
    expect(document.documentElement.style.getPropertyValue('--ui-font-size')).toBe(
      `${UI_FONT_SIZE_BASE_PX * 1.5}px`,
    )
  })

  it('ohne Register bleibt die Basis-Grösse und Bewegung an', () => {
    applyDeepAppearance()
    expect(document.documentElement.style.getPropertyValue('--ui-font-size')).toBe(
      `${UI_FONT_SIZE_BASE_PX}px`,
    )
    expect(document.documentElement.classList.contains('no-motion')).toBe(false)
  })
})

describe('useDeepSelect', () => {
  it('liefert den Registerwert und erneut, wenn er sich aendert', () => {
    const { result, rerender } = renderHook(() => useDeepSelect('chat.details_mode', 'expanded'))
    expect(result.current).toBe('expanded')
    seedDeepSettings([{ key: 'chat', fields: [field('chat.details_mode', 'select', 'collapsed')] }])
    rerender()
    expect(result.current).toBe('collapsed')
  })
})

describe('initDeepSettings', () => {
  it('holt das Register von /api/settings und wendet es an', async () => {
    vi.mocked(getSettings).mockResolvedValueOnce({
      provider: { type: 'local_ollama', model: 'x' },
      deep: sections,
    } as never)
    await initDeepSettings()
    expect(document.documentElement.classList.contains('no-motion')).toBe(true)
  })

  it('wirft nicht, wenn das Backend fehlt', async () => {
    vi.mocked(getSettings).mockRejectedValueOnce(new Error('offline'))
    await expect(initDeepSettings()).resolves.toBeUndefined()
    expect(document.documentElement.classList.contains('no-motion')).toBe(false)
  })
})
