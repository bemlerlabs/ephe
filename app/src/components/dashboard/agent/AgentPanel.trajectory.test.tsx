/**
 * P6 wave A (Ephe norm, ref-12): the trajectory pane — a header with summary,
 * search, expand menu and refresh (task A3), then subgrid + virtualizer (A4),
 * sticky call headers (A5), step rows with sections/overlay/states (A6).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { patchHeight, renderTab } from './trajectoryTestHelpers'
import { useChatStore } from '@/store/chatStore'
import { getTrajectory } from '@/lib/api'

// Fixture: 2 turns of 7 steps = 14 calls; usage sum 144,794+115+8,021,000+119,797 = 8,285,706 tok.
// A function (not a const), so the vi.mock hoisting moment already sees it.
function fixtureTurns() {
  const step = (n: number, usage?: { in: number; out: number }) => ({
    n,
    type: usage ? 'tool_call' : 'message',
    title: `cmd ${n}`,
    ms: 520 + n,
    state: 'ok',
    ...(usage ? { usage: { ...usage, model: 'qwen3.8-flash-next' } } : {}),
  })
  const turn = (offset: number, usage: { in: number; out: number }) => ({
    sid: 's1',
    model: 'qwen3.8-flash-next',
    ts: 1761806357,
    duration_ms: 3520,
    steps: Array.from({ length: 7 }, (_, i) => step(offset + i + 1, i === 0 ? usage : undefined)),
  })
  return [turn(0, { in: 144794, out: 115 }), turn(7, { in: 8021000, out: 119797 })]
}

vi.mock('@/lib/api', () => {
  return {
    getTrajectory: vi.fn(async () => ({ turns: fixtureTurns() })),
    getSubagent: vi.fn(async () => null),
    listMemory: vi.fn(async () => ({ entries: [] })),
    searchMemory: vi.fn(async () => ({ results: [] })),
    getSettings: vi.fn(async () => ({ workspace_dir: null })),
    listArtifacts: vi.fn(async () => ({ artifacts: [], total: 0 })),
  }
})

const sprache = vi.hoisted(() => ({ current: 'en' }))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: sprache.current } }),
}))

describe('TrajectoryTab Kopf (P6 A3, ref-12)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    patchHeight('offsetHeight')
    patchHeight('clientHeight')
  })

  it('Summary-Zeile im Summary-Format: calls, Tausenderpunkt-Tokens, Modell', async () => {
    renderTab()
    const line = await screen.findByTestId('trajectory-summary')
    expect(line.textContent).toBe('14 calls · 8,285,706 tok · qwen3.8-flash-next')
  })

  it('Kopf traegt genau sechs Icon-Buttons', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    const head = screen.getByTestId('trajectory-header')
    expect(head.querySelectorAll('button').length).toBe(6)
  })

  it('Suche-Umschalter zeigt Input; Enter mit Match springt ohne Absturz', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    expect(screen.queryByTestId('trajectory-search')).toBeNull()
    fireEvent.click(screen.getByTestId('trajectory-btn-search'))
    const input = await screen.findByTestId('trajectory-search')
    fireEvent.change(input, { target: { value: 'cmd 8' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect((input as HTMLInputElement).value).toBe('cmd 8')
  })

  it('Fehlerfall: role=alert mit text-destructive-Ton (kein verschlucktes .catch)', async () => {
    vi.mocked(getTrajectory).mockRejectedValueOnce(new Error('boom'))
    renderTab()
    const alert = await screen.findByRole('alert')
    expect(alert.className).toContain('text-destructive')
    expect(alert.textContent).toContain('boom')
  })

  it('the error surface names the next step: the retry button re-pulls and clears the alert', async () => {
    vi.mocked(getTrajectory).mockRejectedValueOnce(new Error('boom'))
    renderTab()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('boom')
    const retry = screen.getByTestId('trajectory-retry')
    expect(retry.textContent).toBe('agentPanel.retry')

    const before = vi.mocked(getTrajectory).mock.calls.length
    fireEvent.click(retry)
    expect(vi.mocked(getTrajectory).mock.calls.length).toBeGreaterThan(before)
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(await screen.findByTestId('trajectory-summary')).toBeTruthy()
  })

  it('Refresh-Button zieht die Trajektorie erneut', async () => {
    const before = vi.mocked(getTrajectory).mock.calls.length
    renderTab()
    await screen.findByTestId('trajectory-summary')
    fireEvent.click(screen.getByTestId('trajectory-btn-refresh'))
    await waitFor(() => {
      expect(vi.mocked(getTrajectory).mock.calls.length).toBeGreaterThan(before)
    })
  })
})

// P6 A4: subgrid timeline + virtualisation — with 80 turns only the overscan
// window may stand in the DOM, and the ghost li reserves the number column.
describe('TrajectoryTab Subgrid + Virtualizer (P6 A4)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    patchHeight('offsetHeight')
    patchHeight('clientHeight')
    const big = Array.from({ length: 80 }, (_, t) => ({
      sid: 's1',
      model: 'm',
      ts: 1761806357 + t,
      duration_ms: 1000 + t,
      steps: Array.from({ length: 5 }, (_, i) => ({
        n: i + 1,
        type: 'message',
        title: `turn ${t} step ${i}`,
        ms: 10 + i,
        state: 'ok',
      })),
    }))
    vi.mocked(getTrajectory).mockResolvedValue({ turns: big })
  })

  afterEach(() => {
    vi.mocked(getTrajectory).mockResolvedValue({ turns: fixtureTurns() })
  })

  it('virtualisiert: nur overscan-Fenster im DOM, Geister-li vorhanden', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    const calls = document.querySelectorAll('[data-trajectory-call]')
    expect(calls.length).toBeGreaterThan(0)
    expect(calls.length).toBeLessThan(80)
    // 600px viewport / 240px estimate + overscan 3 -> at most ~6 rows
    expect(calls.length).toBeLessThanOrEqual(8)
    expect(document.querySelector('[data-testid="trajectory-ghost"]')).toBeTruthy()
  })

  it('DOM-Kontrakt: ol-Grid mit drei Spalten, article in subgrid', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    const ol = document.querySelector('[data-testid="trajectory-list"]')
    expect(ol?.className).toContain('grid-cols-[max-content_minmax(0,1fr)_auto]')
    const article = document.querySelector('[data-trajectory-call]')
    expect(article?.className).toContain('col-span-full')
    expect(article?.className).toContain('grid-cols-subgrid')
  })
})

// P6 A5: sticky call heads — the turn head row sticks, number via padStart-2,
// right-hand metadata from the usage step (IN/OUT tokens, fmtMs, fmtClock).
describe('TrajectoryTab Sticky-Call-Koepfe (P6 A5)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    patchHeight('offsetHeight')
    patchHeight('clientHeight')
    vi.mocked(getTrajectory).mockResolvedValue({ turns: fixtureTurns() })
  })

  it('Turn-Kopf sticky mit padStart-Nummer 01', async () => {
    renderTab()
    const head = await screen.findByTestId('trajectory-turn-head-0')
    expect(head.className).toContain('sticky')
    expect(head.className).toContain('top-0')
    expect(head.textContent).toContain('01')
  })

  it('Rechts-Metadaten aus usage-Step: IN/OUT fmtTokens, fmtMs, fmtClock (Lokalzeit)', async () => {
    renderTab()
    const meta = await screen.findByTestId('trajectory-turn-meta-0')
    const clock = new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      hourCycle: 'h23',
    }).format(new Date(1761806357 * 1000))
    expect(meta.textContent).toBe(`IN 144,794 · OUT 115 · 521ms · ${clock}`)
    // The rendered stamp follows the runner's timezone, so this asserts the format only.
    const stamp = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'medium' }).format(
      new Date(1761806357 * 1000),
    )
    expect(meta.getAttribute('title')).toBe(stamp)
  })
  it('Zweiter Turn traegt Nummer 02', async () => {
    renderTab()
    const head = await screen.findByTestId('trajectory-turn-head-1')
    expect(head.textContent).toContain('02')
  })
})

// P6 A6: step rows with section titles, role colours, right-hand metadata
// (fmtMs + full timestamp + copy + chevron), IN/OUT sections with
// rounded-lg border border-card-border and a floating ⤢ overlay.
describe('TrajectoryTab Step-Zeilen + Sektionen (P6 A6)', () => {
  beforeEach(() => {
    useChatStore.setState({ activeSessionId: 's1' })
    patchHeight('offsetHeight')
    patchHeight('clientHeight')
    vi.mocked(getTrajectory).mockResolvedValue({ turns: fixtureTurns() })
  })

  afterEach(() => {
    vi.mocked(getTrajectory).mockResolvedValue({ turns: fixtureTurns() })
  })

  it('Alt-Zeilen-Klassifikation: ungerade bg-surface/30, gerade ohne', async () => {
    renderTab()
    await screen.findByTestId('trajectory-summary')
    const odd = await screen.findByTestId('trajectory-step-0-2')
    const even = await screen.findByTestId('trajectory-step-0-1')
    expect(odd.className).toContain('bg-surface/30')
    expect(even.className).not.toContain('bg-surface/30')
    expect(odd.className).toContain('grid-cols-subgrid')
    expect(odd.className).toContain('min-h-8')
  })

  it('TYPE-Label traegt die Rollenfarbe aus A1', async () => {
    renderTab()
    const type = await screen.findByTestId('trajectory-step-type-0-1')
    expect(type.className).toContain('text-trajectory-tool-call')
    expect(type.textContent).toBe('tool_call')
    const msg = await screen.findByTestId('trajectory-step-type-0-2')
    expect(msg.className).toContain('text-trajectory-assistant')
  })

  it('Step-Zeile rechts: fmtMs + Volltimestamp-Titel + Copy + Chevron', async () => {
    renderTab()
    const meta = await screen.findByTestId('trajectory-step-meta-0-1')
    expect(meta.textContent).toContain('521ms')
    // The rendered clock depends on the runner's timezone, so this asserts the
    // format the surface promises.
    const expected = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'medium' }).format(
      new Date(1761806357 * 1000),
    )
    expect(meta.getAttribute('title')).toBe(expected)
    expect(document.querySelector('[data-testid="trajectory-copy-0-1"]')).toBeTruthy()
    expect(document.querySelector('[data-testid="trajectory-chevron-0-1"]')).toBeTruthy()
  })

  it('Klick auf Step-Zeile oeffnet IN/OUT-Sektionen mit border-card-border und ⤢-Overlay', async () => {
    renderTab()
    const line = await screen.findByTestId('trajectory-step-0-1')
    fireEvent.click(line)
    const secIn = await screen.findByTestId('trajectory-section-0-1-in')
    const secOut = await screen.findByTestId('trajectory-section-0-1-out')
    expect(secIn.className).toContain('border-card-border')
    expect(secOut.className).toContain('border-card-border')
    const pre = document.querySelector('[data-testid="trajectory-code-0-1-in"]')
    expect(pre?.className).toContain('bg-surface')
    expect(pre?.className).toContain('max-h-64')
    expect(document.querySelector('[data-testid="trajectory-code-expand-0-1-in"]')).toBeTruthy()
  })

  it('⤢-Overlay oeffnet den Code-Block auf Pane-Hoehe (max-h-none)', async () => {
    renderTab()
    const line = await screen.findByTestId('trajectory-step-0-1')
    fireEvent.click(line)
    const pre = await screen.findByTestId('trajectory-code-0-1-in')
    expect(pre.className).toContain('max-h-64')
    fireEvent.click(screen.getByTestId('trajectory-code-expand-0-1-in'))
    const opened = await screen.findByTestId('trajectory-code-0-1-in')
    expect(opened.className).toContain('max-h-none')
  })

  it('Sektions-Leer: p-3 text-ui-sm text-foreground-subtlest bei leerem Inhalt', async () => {
    vi.mocked(getTrajectory).mockResolvedValue({
      turns: [
        {
          sid: 's1',
          model: 'm',
          ts: 1761806357,
          duration_ms: 100,
          steps: [{ n: 1, type: 'tool_result', title: '', ms: 10, state: 'ok' }],
        },
      ],
    })
    renderTab()
    const line = await screen.findByTestId('trajectory-step-0-1')
    fireEvent.click(line)
    const empty = await screen.findByTestId('trajectory-section-empty-0-1-in')
    expect(empty.className).toContain('text-foreground-subtlest')
    expect(empty.className).toContain('p-3')
  })

  it('Sektionstitel nach Rolle: TOOL RESULT OUTPUT / ASSISTANT Reasoning / USER', async () => {
    vi.mocked(getTrajectory).mockResolvedValue({
      turns: [
        {
          sid: 's1',
          model: 'm',
          ts: 1761806357,
          duration_ms: 100,
          steps: [
            { n: 1, type: 'user', title: 'hi', ms: 10, state: 'ok' },
            { n: 2, type: 'reasoning', title: 'denk', ms: 10, state: 'ok' },
            { n: 3, type: 'tool_result', title: 'out', ms: 10, state: 'ok' },
          ],
        },
      ],
    })
    renderTab()
    fireEvent.click(await screen.findByTestId('trajectory-step-0-1'))
    expect((await screen.findByTestId('trajectory-section-0-1-in')).textContent).toContain('USER')
    fireEvent.click(screen.getByTestId('trajectory-step-0-2'))
    expect((await screen.findByTestId('trajectory-section-0-2-in')).textContent).toContain(
      'ASSISTANT Reasoning',
    )
    fireEvent.click(screen.getByTestId('trajectory-step-0-3'))
    expect((await screen.findByTestId('trajectory-section-0-3-in')).textContent).toContain(
      'TOOL RESULT OUTPUT',
    )
  })

  it('Textkoerper (P6): USER-Text als IN, Reasoning/Output als OUT', async () => {
    vi.mocked(getTrajectory).mockResolvedValue({
      turns: [
        {
          sid: 's1',
          model: 'm',
          ts: 1761806357,
          duration_ms: 100,
          steps: [
            {
              n: 1,
              type: 'USER',
              title: 'Analysiere das Repo',
              ms: 10,
              state: '',
              text: 'Analysiere das Repo vollständig',
            },
            {
              n: 2,
              type: 'THINKING',
              title: 'denk',
              ms: 10,
              state: '',
              text: 'Ich untersuche zuerst die Struktur.',
            },
            {
              n: 3,
              type: 'TOOL_DONE',
              title: 'run_shell',
              ms: 10,
              state: '',
              text: '3 Dateien gefunden',
            },
          ],
        },
      ],
    })
    renderTab()
    // USER step: IN shows the full text body, OUT is an empty section
    fireEvent.click(await screen.findByTestId('trajectory-step-0-1'))
    const userIn = await screen.findByTestId('trajectory-code-0-1-in')
    expect(userIn.textContent).toBe('Analysiere das Repo vollständig')
    fireEvent.click(screen.getByTestId('trajectory-step-0-2'))
    const thinkOut = await screen.findByTestId('trajectory-code-0-2-out')
    expect(thinkOut.textContent).toBe('Ich untersuche zuerst die Struktur.')
    fireEvent.click(screen.getByTestId('trajectory-step-0-3'))
    const toolOut = await screen.findByTestId('trajectory-code-0-3-out')
    expect(toolOut.textContent).toBe('3 Dateien gefunden')
    // role colors for the new types (case-insensitive)
    expect(screen.getByTestId('trajectory-step-type-0-1').className).toContain(
      'text-trajectory-user',
    )
    expect(screen.getByTestId('trajectory-step-type-0-2').className).toContain(
      'text-trajectory-reasoning',
    )
  })

  it('Empty-State zentriert mit leerem Text', async () => {
    vi.mocked(getTrajectory).mockResolvedValue({ turns: [] })
    renderTab()
    const box = await screen.findByTestId('trajectory-empty')
    expect(box.className).toContain('flex-col')
    expect(box.className).toContain('items-center')
    expect(box.className).toContain('px-4')
    expect(box.className).toContain('py-10')
    expect(box.textContent).toContain('agentPanel.trajectoryEmpty')
  })
})
