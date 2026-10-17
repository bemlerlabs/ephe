import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SkyPanel, SkyStatusLine, computeTokensByDay } from '@/components/dashboard/SkyCard'
import type { SkyData } from '@/lib/api'
import type { Session } from '@/types'

// Owner feedback 2026-09-28: the ephemerides as their OWN section inside the
// settings hub (no longer on the welcome screen) — orbits AND token usage
// per day (bars, estimated locally from the session store). Fail-soft.

vi.mock('@/lib/api', () => ({
  getSky: vi.fn(),
}))

const MOCK_SESSIONS: Session[] = [
  {
    id: 's1',
    title: 'heute',
    createdAt: Date.now(),
    messages: [
      {
        id: 'm1',
        role: 'user',
        content: 'Hallo Welt, diese Nachricht hat einige Token.',
        timestamp: new Date('2026-09-28T10:00:00').getTime(),
      },
      {
        id: 'm2',
        role: 'assistant',
        content: 'Und die Antwort ebenso, plus Thinking.',
        thinking: { text: 'kurzes Nachdenken' } as never,
        timestamp: new Date('2026-09-28T10:00:30').getTime(),
      },
    ],
  },
  {
    id: 's2',
    title: 'gestern',
    createdAt: Date.now() - 86_400_000,
    messages: [
      {
        id: 'm3',
        role: 'user',
        content: 'Nachricht von gestern.',
        timestamp: new Date('2026-09-27T09:00:00').getTime(),
      },
    ],
  },
]

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (s: { sessions: Session[] }) => unknown) => sel({ sessions: MOCK_SESSIONS }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) => {
      if (!vars) return key
      return `${key}:${JSON.stringify(vars)}`
    },
    i18n: { language: 'en' },
  }),
}))

import { getSky } from '@/lib/api'
const mockGetSky = vi.mocked(getSky)

const TODAY = '2026-09-28'

const SKY_BUSY: SkyData = {
  available: true,
  days: 7,
  today: TODAY,
  empty: false,
  total: 12,
  faded: 3,
  kinds: { session: 4, tool: 7, artifact: 1 },
  rows: [
    {
      d: TODAY,
      weekday: 'Mo',
      label: '28.09',
      total: 8,
      peak_hour: 14,
      hours: { 9: 3, 14: 5 },
    },
    ...Array.from({ length: 6 }, (_, i) => ({
      d: `2026-09-2${1 + i}`,
      weekday: 'So',
      label: `2${1 + i}.09`,
      total: 0,
      peak_hour: null,
      hours: {},
    })),
  ],
}

describe('computeTokensByDay (lokale Token-Schätzung je Kalendertag)', () => {
  it('summiert content + thinking je Tag in Lokalzeit', () => {
    const byDay = computeTokensByDay(MOCK_SESSIONS)
    expect(Object.keys(byDay).sort()).toEqual(['2026-09-27', TODAY])
    // The same formula as the context meter: estimateTokens over both messages.
    const chars =
      'Hallo Welt, diese Nachricht hat einige Token.'.length +
      ('Und die Antwort ebenso, plus Thinking.' + 'kurzes Nachdenken').length
    const expected = Math.ceil(chars / 4.2)
    expect(byDay[TODAY]).toBeGreaterThanOrEqual(expected - 2)
    expect(byDay[TODAY]).toBeLessThanOrEqual(expected + 2)
    expect(byDay['2026-09-27']).toBeGreaterThan(0)
  })

  it('leerer Store → leere Map, kein Wurf', () => {
    expect(computeTokensByDay([])).toEqual({})
  })
})

describe('SkyPanel (Settings-Tab Ephemeriden)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('zeigt Übersicht + 7 Tageszeilen mit Stunden-Gitter und Token-Balken', async () => {
    mockGetSky.mockResolvedValue(SKY_BUSY)
    render(<SkyPanel />)
    const panel = await screen.findByTestId('sky-panel')
    expect(panel.textContent).toContain('sky.total')
    const grids = panel.querySelectorAll('[role="img"]')
    expect(grids.length).toBe(7)
    grids.forEach((g) => expect(g.children.length).toBe(24))
    // token bar (div.h-1.5) per day
    expect(panel.querySelectorAll('.h-1\\.5').length).toBe(7)
    expect(panel.textContent).toContain('tok')
  })

  it('heutiger Token-Balken gewichtet relativ zum stärksten Tag', async () => {
    mockGetSky.mockResolvedValue(SKY_BUSY)
    render(<SkyPanel />)
    const dayRow = await screen.findByTestId(`sky-day-${TODAY}`)
    const bar = dayRow.querySelector('.h-1\\.5 > div') as HTMLElement
    expect(bar).toBeTruthy()
    expect(Number(bar.style.width.replace('%', ''))).toBeGreaterThan(0)
  })

  it('Backend-Störung (available=false): ehrlicher Fail-Text, keine erfundenen Zahlen', async () => {
    mockGetSky.mockResolvedValue({ ...SKY_BUSY, available: false, rows: [] })
    render(<SkyPanel />)
    await waitFor(() => expect(screen.getByText('settings.healthFail')).toBeTruthy())
    expect(screen.queryByTestId('sky-chart')).toBeNull()
  })

  it('Netzwerk-Fehler: ehrlicher Fail-Text', async () => {
    mockGetSky.mockRejectedValue(new Error('offline'))
    render(<SkyPanel />)
    await waitFor(() => expect(screen.getByText('settings.healthFail')).toBeTruthy())
  })
})

describe('SkyStatusLine (Status-Popover)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('Heute- und Wochen-Bahnen aus den Zeilen gerechnet', async () => {
    mockGetSky.mockResolvedValue(SKY_BUSY)
    render(<SkyStatusLine />)
    const line = await screen.findByTestId('sky-status-line')
    expect(line.textContent).toContain('"today":8')
    expect(line.textContent).toContain('"week":12')
  })

  it('offline: keine Zeile', async () => {
    mockGetSky.mockRejectedValue(new Error('offline'))
    render(<SkyStatusLine />)
    await waitFor(() => expect(screen.queryByTestId('sky-status-line')).toBeNull())
  })
})
