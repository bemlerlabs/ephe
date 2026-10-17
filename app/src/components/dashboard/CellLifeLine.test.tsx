/**
 * WP5 — the life line may only say what the registry knows.
 *
 * The case before WP5: `core.ephemeral_cell` was only ever called from tests. A
 * line "cell running" would therefore have been a claim about something that
 * never ran. These tests pin the three states: assert nothing before there is a
 * cell; its real numbers while it lives; one word once it has evaporated.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'
import { CellLifeLine } from './CellLifeLine'
import { getCellLife } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  getCellLife: vi.fn(async () => ({ cell: { alive: false, calls: 0, avg_ms: null } })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'de' },
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${JSON.stringify(opts)}` : key,
  }),
}))

const alive = (over: Record<string, unknown> = {}) => ({
  cell: {
    alive: true,
    ordinal: 12,
    kind: 'wasi',
    calls: 4,
    avg_ms: 0.485,
    age_seconds: 61.5,
    idle_seconds: 1.2,
    ttl_seconds: 1800,
    seconds_left: 1798.8,
    ...over,
  },
})

const settled = async () => {
  // Fake timers and `findBy*` bite each other (waitFor polls on the same timers);
  // so push everything through the clock ourselves and read it off directly.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

describe('CellLifeLine — nur Zahlen aus der Cell-Registry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('behauptet nichts, solange die Session keine Zelle hat', async () => {
    render(<CellLifeLine sessionId="s" />)
    await settled()
    expect(screen.queryByTestId('cell-life-line')).toBeNull()
    expect(screen.queryByTestId('cell-life-gone')).toBeNull()
  })

  it('zeigt Nummer, Mittelwert und Zustand — den Mittelwert mit Locale-Komma', async () => {
    ;(getCellLife as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(alive())
    render(<CellLifeLine sessionId="s" />)
    await settled()
    const line = screen.getByTestId('cell-life-line')
    expect(line.textContent).toContain('"ordinal":12')
    expect(line.textContent).toContain('"ms":"0,485"')
    expect(screen.getByTestId('cell-life-state').textContent).toContain('chat.cellRunning')
    expect(screen.getByTestId('cell-life-left').textContent).toContain('chat.cellLeft')
    // The countdown changes with every tick — only the state is announced.
    expect(screen.getByTestId('cell-life-state').getAttribute('aria-live')).toBe('polite')
    expect(screen.getByTestId('cell-life-left').getAttribute('aria-live')).toBeNull()
    // R1 put the line on text-status-info/60 = below 4.5:1 contrast on paper.
    expect(line.className).toContain('text-ink-faint')
    expect(line.className).toContain('ephe-condense')
  })

  it('heisst ruht, sobald die Muße länger als der Takt ist', async () => {
    ;(getCellLife as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      alive({ idle_seconds: 30 }),
    )
    render(<CellLifeLine sessionId="s" />)
    await settled()
    expect(screen.getByTestId('cell-life-state').textContent).toContain('chat.cellResting')
  })

  it('lässt die Zeile zerfallen und nennt dann die Verdunstung', async () => {
    const mock = getCellLife as unknown as ReturnType<typeof vi.fn>
    mock.mockResolvedValueOnce(alive())
    render(<CellLifeLine sessionId="s" />)
    await settled()
    expect(screen.getByTestId('cell-life-line')).toBeTruthy()

    mock.mockResolvedValueOnce({ cell: { alive: false, calls: 0, avg_ms: null } })
    await settled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(screen.getByTestId('cell-life-line').className).toContain('ephe-decay')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600)
    })
    expect(screen.getByTestId('cell-life-gone')).toBeTruthy()
    expect(screen.queryByTestId('cell-life-line')).toBeNull()
  })

  it('fragt nicht, wenn niemand hinsieht', async () => {
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    render(<CellLifeLine sessionId="s" />)
    await settled()
    expect(getCellLife).not.toHaveBeenCalled()
    hidden.mockRestore()
  })
})
