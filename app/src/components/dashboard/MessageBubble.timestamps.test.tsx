// I3-4: appearance.show_timestamps is a control, not decoration.
// The timestamp was always rendered — the settings tab offered a switch that
// nobody read. Now the line lives in one place and follows the tab's value.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

import MessageBubble from '@/components/dashboard/MessageBubble'
import { seedDeepSettings } from '@/lib/deepSettings'
import type { ChatMessage } from '@/types'
import type { DeepSection } from '@/types'

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => (
    <div data-testid="markdown">{String(children)}</div>
  ),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: React.ReactNode }) => <pre>{children}</pre>,
}))
// The bubble's clock is not asserted as a string here (that would repeat Intl in
// the test); the two hoisted cells record what the interface reports and what the
// bubble hands to the formatter. The per-language reading itself lives in
// src/lib/utils.test.ts with a literal expectation per language.
const sprache = vi.hoisted(() => ({ current: 'de' }))
const uebergeben = vi.hoisted(() => ({ language: '' }))

vi.mock('@/lib/utils', () => ({
  formatTime: (_date: unknown, language?: string) => {
    uebergeben.language = language ?? ''
    return '12:00'
  },
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: (() => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'count' in vars ? `${key}:${String(vars.count)}` : key,
    i18n: { language: sprache.current },
  })) as never,
}))

const MSG = {
  id: 'a1',
  role: 'assistant',
  content: 'hallo',
  timestamp: 0,
} as ChatMessage

function register(show: boolean) {
  seedDeepSettings([
    {
      key: 'appearance',
      fields: [
        {
          key: 'appearance.show_timestamps',
          type: 'bool',
          label: 'Zeitstempel anzeigen',
          labelEn: 'Show timestamps',
          default: true,
          value: show,
        },
      ],
    } as DeepSection,
  ])
}

beforeEach(() => seedDeepSettings(null))

describe('appearance.show_timestamps (I3-4)', () => {
  it('zeigt die Zeit, wenn der Schalter an ist', () => {
    register(true)
    render(<MessageBubble message={MSG} />)
    expect(screen.getByTestId('message-timestamp').textContent).toBe('12:00')
  })

  it('zeigt sie nicht, wenn der Schalter aus ist', () => {
    register(false)
    render(<MessageBubble message={MSG} />)
    expect(screen.queryByTestId('message-timestamp')).toBeNull()
  })

  it('ohne Register bleibt die Zeit sichtbar (Default wie vor I3-4)', () => {
    render(<MessageBubble message={MSG} />)
    expect(screen.getByTestId('message-timestamp')).toBeTruthy()
  })
})

// Wave #55: the bubble must pass the interface language to the clock. Measured in
// both states — a repair that only worked in English would be the same defect
// with the signs swapped.
describe('MessageBubble clock — counter-check #55', () => {
  it('german interface: the bubble formats in de', () => {
    sprache.current = 'de'
    render(<MessageBubble message={MSG} />)
    expect(uebergeben.language).toBe('de')
  })

  it('english interface: the bubble formats in en', () => {
    sprache.current = 'en'
    render(<MessageBubble message={MSG} />)
    expect(uebergeben.language).toBe('en')
    sprache.current = 'de'
  })
})
