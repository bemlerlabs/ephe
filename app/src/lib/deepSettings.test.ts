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
  useChatReadingWidth,
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
      field('appearance.chat_font_scale', 'number', 120, { min: 80, max: 150 }),
      field('appearance.reading_width', 'number', 1024, { min: 480, max: 1200 }),
      field('appearance.animations_enabled', 'bool', false),
      field('appearance.show_timestamps', 'bool', true),
    ],
  },
]

beforeEach(() => {
  document.documentElement.style.removeProperty('--ui-font-size')
  document.documentElement.style.removeProperty('--chat-font-size')
  document.documentElement.style.removeProperty('--chat-reading-width')
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

  it('carries the chosen base step (13 px) into both type steps', () => {
    seedDeepSettings([
      {
        key: 'appearance',
        fields: [
          field('appearance.font_scale', 'number', 100, { min: 80, max: 150 }),
          field('appearance.chat_font_scale', 'number', 100, { min: 80, max: 150 }),
          field('appearance.base_font_px', 'select', '13'),
        ],
      },
    ])
    expect(document.documentElement.style.getPropertyValue('--ui-font-size')).toBe('13px')
    // the conversation step keeps its two-pixel step under the base
    expect(document.documentElement.style.getPropertyValue('--chat-font-size')).toBe('11px')
  })

  it('ignores a base step outside 13/14/15 and keeps the shipped 15 px', () => {
    seedDeepSettings([
      {
        key: 'appearance',
        fields: [
          field('appearance.font_scale', 'number', 100, { min: 80, max: 150 }),
          field('appearance.base_font_px', 'select', '22'),
        ],
      },
    ])
    expect(document.documentElement.style.getPropertyValue('--ui-font-size')).toBe(
      `${UI_FONT_SIZE_BASE_PX}px`,
    )
  })

  it('scales the conversation step from the interface and chat factors', () => {
    seedDeepSettings(sections)
    expect(document.documentElement.style.getPropertyValue('--chat-font-size')).toBe('23.4px')
    expect(document.documentElement.style.getPropertyValue('--chat-reading-width')).toBe('1024px')
  })

  it('clamps the conversation step and the reading width to the register bounds', () => {
    seedDeepSettings([
      {
        key: 'appearance',
        fields: [
          field('appearance.font_scale', 'number', 100),
          field('appearance.chat_font_scale', 'number', 4000),
          field('appearance.reading_width', 'number', 100),
        ],
      },
    ])
    expect(document.documentElement.style.getPropertyValue('--chat-font-size')).toBe('19.5px')
    expect(document.documentElement.style.getPropertyValue('--chat-reading-width')).toBe('480px')
  })

  it('applies the curated accent to the root and falls back to ember', () => {
    seedDeepSettings([
      { key: 'appearance', fields: [field('appearance.accent', 'select', 'indigo')] },
    ])
    expect(document.documentElement.dataset.accent).toBe('indigo')
    seedDeepSettings([
      { key: 'appearance', fields: [field('appearance.accent', 'select', 'neon')] },
    ])
    expect(document.documentElement.dataset.accent).toBe('ember')
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

describe('useChatReadingWidth', () => {
  it('follows a seeded reading width', () => {
    const { result, rerender } = renderHook(() => useChatReadingWidth())
    expect(result.current).toBe(768)
    seedDeepSettings([
      { key: 'appearance', fields: [field('appearance.reading_width', 'number', 600)] },
    ])
    rerender()
    expect(result.current).toBe(600)
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

describe('the unchosen chat step', () => {
  it('reads at 16px instead of borrowing the interface step', () => {
    seedDeepSettings([
      { key: 'appearance', fields: [field('appearance.font_scale', 'number', 100)] },
    ])
    expect(document.documentElement.style.getPropertyValue('--chat-font-size')).toBe('16px')
  })

  it('keeps a chosen step, even a smaller one', () => {
    seedDeepSettings([
      {
        key: 'appearance',
        fields: [
          field('appearance.font_scale', 'number', 100),
          field('appearance.chat_font_scale', 'number', 80),
        ],
      },
    ])
    expect(document.documentElement.style.getPropertyValue('--chat-font-size')).toBe('10.4px')
  })
})
