/**
 * I1-9 (audit truth): the audit tab shows the decision, not just the status.
 *
 * A blocked command was not executed. If the row still says "ok" and glows green,
 * the app tells the user the opposite of what the machine just prevented — and
 * that is what the log is there for.
 *
 * Side finding of this wave: the tab hung off NO route — panel.tsx showed the
 * trajectory replay under the key 'audit'. WP5 (2026-10-04) separated them:
 * 'audit' is the evidence list, 'trajectory' the replay; AgentPanel.tabs.test.tsx
 * guards the wiring.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { AuditTab } from './agent/auditTab'
import {
  AUDIT_KINDS,
  auditClock,
  auditDayKey,
  auditDuration,
  auditErrorCode,
  auditKindLabelKey,
  auditKindName,
  auditSignature,
  auditZoneLabel,
} from './agent/auditFormat'
import { getAudit } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  LAN_TOKEN: null,
  listFs: vi.fn(async () => ({ entries: [] })),
  getAudit: vi.fn(async () => ({ entries: [] })),
}))

// t returns the key and appends the interpolated values — otherwise "80 of 13.813"
// would be invisible in the test, because only the key would get rendered.
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options
        ? `${key} ${Object.entries(options)
            .map(([k, v]) => `${k}=${v}`)
            .join(' ')}`
        : key,
    i18n: { language: 'de' },
  }),
}))

const entry = (over: Record<string, unknown>) => ({
  ts: '2026-10-02T10:00:00.000+00:00',
  kind: 'tool_exec',
  tool: 'run_shell',
  args_hash: 'abc123',
  args: 'command=echo x > /tmp/x',
  decision: '',
  status: 'ok',
  duration_ms: 3,
  detail: '',
  ...over,
})

async function renderWith(entries: unknown[]) {
  ;(getAudit as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ entries })
  render(<AuditTab />)
  return screen.findByTestId('audit-entry-state')
}

describe('I1-9: the blockade is visible in the audit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('a blocked run names the decision over the status', async () => {
    await renderWith([entry({ decision: 'blocked', status: 'ok' })])
    expect(await screen.findByText('blocked')).toBeTruthy()
  })

  it('a blocked run shows the warning dot and never the success colour', async () => {
    const dot = await renderWith([entry({ decision: 'blocked', status: 'ok' })])
    expect(dot.className).toContain('bg-status-warning')
    expect(dot.className).not.toContain('bg-status-success')
    expect(dot.getAttribute('title')).toBe('agentPanel.auditBlocked')
  })

  it('a command that ran free keeps the success colour', async () => {
    const dot = await renderWith([entry({ decision: '', status: 'ok' })])
    expect(dot.className).toContain('bg-status-success/70')
    expect(dot.getAttribute('title')).toBeNull()
    expect(await screen.findByText('ok')).toBeTruthy()
  })

  it('a denial keeps the strong warning colour', async () => {
    const dot = await renderWith([entry({ decision: 'denied', status: 'ok' })])
    expect(dot.className).toContain('bg-status-danger')
  })
})

/**
 * R2-H (evidence chain): the tab promises "tool, signature short form, duration,
 * result" in its tip. Two of those only sat in the log — without them the chain is
 * readable but not comparable: the same short form == the same call, and without a
 * duration "it ran" is no evidence of effort.
 */
describe('R2-H: signature and duration stand in the row', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('the row shows the signature short form and the call duration', async () => {
    await renderWith([entry({ args_hash: 'abcdef0123456789', duration_ms: 485 })])
    const sig = await screen.findByTestId('audit-entry-signature')
    expect(sig.textContent).toBe('#abcdef01')
    expect(sig.getAttribute('title')).toContain('abcdef0123456789')
    const dur = await screen.findByTestId('audit-entry-duration')
    expect(dur.textContent).toBe('485 ms')
  })

  it('the argument short form stays and the signature appears beside it', async () => {
    await renderWith([entry({ args: 'command=echo x > /tmp/x', args_hash: 'abcdef0123456789' })])
    expect(await screen.findByText('command=echo x > /tmp/x')).toBeTruthy()
    expect((await screen.findByTestId('audit-entry-signature')).textContent).toBe('#abcdef01')
  })

  it('without a measured duration the row invents no number', async () => {
    await renderWith([entry({ duration_ms: null })])
    await screen.findByTestId('audit-entry-state')
    expect(screen.queryByTestId('audit-entry-duration')).toBeNull()
  })

  it('the signature is missing only when the log has none, even with empty args', async () => {
    await renderWith([entry({ args: '', args_hash: 'ff00ff00ff00ff00' })])
    expect((await screen.findByTestId('audit-entry-signature')).textContent).toBe('#ff00ff00')
  })

  it('duration and short form come in the shapes the row needs', () => {
    expect(auditDuration(3, 'de')).toBe('3 ms')
    expect(auditDuration(1500, 'de')).toBe('1,5 s')
    expect(auditDuration(61500, 'de')).toBe('61,5 s')
    expect(auditDuration(null, 'de')).toBe('')
    expect(auditDuration(undefined, 'de')).toBe('')
    expect(auditSignature('abcdef0123456789')).toBe('#abcdef01')
    expect(auditSignature('')).toBe('')
    expect(auditSignature(undefined)).toBe('')
  })
})

/* ── N1: the evidence chain ───────────────────────────────────────────────
 * Eight findings, one yardstick: the surface shows what is in the log — local
 * time instead of raw UTC, day grouping instead of a date jump, the kind as its
 * own piece, a filter over the whole schema, the page as a share of the total, an
 * error that is not an empty log, a loading state and one number-format rule.
 */

/** local HH:MM:SS — the same rule fmtClock applies in the row and the header. */
const LOCAL_CLOCK = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
  hourCycle: 'h23',
})
const localClock = (ts: string) => LOCAL_CLOCK.format(new Date(ts))
const localDayKey = (ts: string) => {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** What GET /api/audit answers to the surface (total_matching is the new field). */
type AuditReply = { entries: unknown[]; total_matching?: number }

async function renderResponse(payload: AuditReply) {
  ;(getAudit as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(payload)
  render(<AuditTab />)
  // audit-count is present as soon as an answer arrives — even with zero rows.
  return screen.findByTestId('audit-count')
}

describe('N1.1: the time basis is local and named in the header', () => {
  it('the row shows local time over the raw UTC from the log', async () => {
    const ts = '2026-10-05T09:46:40.123+00:00'
    await renderResponse({ entries: [entry({ ts })] })
    const clock = await screen.findByTestId('audit-entry-time')
    expect(clock.textContent).toBe(localClock(ts))
    const utc = ts.slice(11, 19)
    if (new Date(ts).getTimezoneOffset() !== 0) {
      expect(clock.textContent).not.toBe(utc)
    }
  })

  it('the head of the list names the zone the sort runs in', async () => {
    await renderResponse({ entries: [entry({})] })
    const basis = await screen.findByTestId('audit-time-basis')
    const zone = auditZoneLabel('de')
    expect(zone).not.toBe('')
    expect(basis.textContent).toContain('agentPanel.auditTimeBasis')
    expect(basis.textContent).toContain(zone)
  })

  it('an unreadable timestamp invents no clock time', () => {
    expect(auditClock('keine-datumsangabe')).toBe('')
    expect(auditClock('2026-10-05T09:46:40.123+00:00')).toBe(
      localClock('2026-10-05T09:46:40.123+00:00'),
    )
  })
})

describe('N1.2: the days stand where the list breaks', () => {
  it('two days give two headings, one day gives one', async () => {
    await renderResponse({
      entries: [
        entry({ ts: '2026-10-05T09:46:40.000+00:00' }),
        entry({ ts: '2026-10-05T07:00:00.000+00:00' }),
        entry({ ts: '2026-10-03T18:10:35.000+00:00' }),
      ],
    })
    await screen.findAllByTestId('audit-entry-row')
    const headings = await screen.findAllByTestId('audit-day-heading')
    expect(headings).toHaveLength(2)
    expect(headings[0]?.textContent).toContain('2026')
  })

  it('the day keys follow the local calendar over the UTC cut', () => {
    expect(auditDayKey('2026-10-05T09:46:40.000+00:00')).toBe(
      localDayKey('2026-10-05T09:46:40.000+00:00'),
    )
    expect(auditDayKey('kaputt')).toBe('')
  })
})

describe('N1.3: the event kind is a piece of its own', () => {
  it('hook and tool_exec on the same tool no longer look the same', async () => {
    await renderResponse({
      entries: [
        entry({ kind: 'tool_exec', tool: 'run_shell' }),
        entry({ kind: 'hook', tool: 'run_shell', duration_ms: null }),
      ],
    })
    const kinds = await screen.findAllByTestId('audit-entry-kind')
    expect(kinds.map((k) => k.textContent)).toEqual([
      'agentPanel.auditKindToolExec',
      'agentPanel.auditKindHook',
    ])
    expect(kinds[0]?.getAttribute('title')).toBe('tool_exec')
    expect(kinds[1]?.getAttribute('title')).toBe('hook')
  })

  it('detail stands on an error-free row with mode and tool count visible', async () => {
    await renderResponse({
      entries: [
        entry({ kind: 'turn', tool: '', status: 'ok', detail: 'mode=full-access tools=35' }),
      ],
    })
    const detail = await screen.findByTestId('audit-entry-detail')
    expect(detail.textContent).toBe('mode=full-access tools=35')
    expect(detail.getAttribute('title')).toBe('mode=full-access tools=35')
  })

  it('an error row stays red', async () => {
    await renderResponse({ entries: [entry({ status: 'error', detail: 'exit 2' })] })
    const detail = await screen.findByTestId('audit-entry-detail')
    expect(detail.className).toContain('text-status-danger')
  })

  it('unknown kinds stay identifiers while known ones get a key', () => {
    expect(auditKindLabelKey('mcp_memory')).toBe('agentPanel.auditKindMcpMemory')
    expect(auditKindName('hook', (k) => k)).toBe('agentPanel.auditKindHook')
    expect(auditKindName('irgendwas_neues', (k) => k)).toBe('irgendwas_neues')
  })
})

describe('N1.4: the filter covers the schema and reads German', () => {
  it('eight kinds plus All, none labelled with a raw schema value', async () => {
    await renderResponse({ entries: [entry({})] })
    const group = await screen.findByRole('group')
    const chips = [...group.querySelectorAll('button[data-kind]')]
    expect(chips).toHaveLength(AUDIT_KINDS.length + 1)
    expect(chips.map((c) => c.getAttribute('data-kind'))).toEqual([
      'all',
      ...(AUDIT_KINDS as unknown as string[]),
    ])
    for (const kind of AUDIT_KINDS) {
      const chip = chips.find((c) => c.getAttribute('data-kind') === kind)!
      expect(chip.textContent).toBe(auditKindLabelKey(kind))
      expect(chip.textContent).not.toBe(kind)
      expect(chip.getAttribute('title')).toBe(kind)
    }
  })

  it('a click filters by the schema value of the log', async () => {
    await renderResponse({ entries: [entry({})] })
    const group = await screen.findByRole('group')
    await act(async () => {
      fireEvent.click(group.querySelector('button[data-kind="plugin_gate"]')!)
    })
    expect(getAudit).toHaveBeenLastCalledWith(80, 'plugin_gate')
    await act(async () => {
      fireEvent.click(group.querySelector('button[data-kind="all"]')!)
    })
    expect(getAudit).toHaveBeenLastCalledWith(80, '')
  })
})

describe('N1.5: the page says how many items sit behind it', () => {
  it('total_matching appears in the line under the filter', async () => {
    await renderResponse({
      entries: [entry({}), entry({ ts: '2026-10-05T09:00:00+00:00' })],
      total_matching: 13813,
    })
    const line = await screen.findByTestId('audit-count')
    expect(line.textContent).toContain('agentPanel.auditCount')
    expect(line.textContent).toContain('2')
    expect(line.textContent).toContain('13.813')
  })

  it('without a backend field the line carries no invented total', async () => {
    await renderResponse({ entries: [entry({})] })
    const line = await screen.findByTestId('audit-count')
    expect(line.textContent).toContain('agentPanel.auditCountNoTotal')
    expect(line.textContent).not.toContain('total=')
  })
})

describe('N1.6: an error is not an empty log', () => {
  it('a 500 shows the error with its status code over the empty-log copy', async () => {
    ;(getAudit as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('API 500: Internal Server Error'),
    )
    render(<AuditTab />)
    const box = await screen.findByTestId('audit-error')
    expect(box.textContent).toContain('agentPanel.auditLoadFailed')
    expect(box.textContent).toContain('HTTP 500')
    expect(box.textContent).toContain('agentPanel.retry')
    expect(screen.queryByText(/agentPanel\.auditEmpty/)).toBeNull()
  })

  it('a refresh failure keeps the last good list on screen', async () => {
    await renderResponse({ entries: [entry({})] })
    await screen.findByTestId('audit-entry-row')
    ;(getAudit as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('API 503: x'),
    )
    fireEvent.click(screen.getByTestId('audit-refresh'))
    await screen.findByTestId('audit-error')
    expect(screen.getAllByTestId('audit-entry-row')).toHaveLength(1)
    expect(screen.getByTestId('audit-count').textContent).toContain('1')
    expect(screen.queryByText(/agentPanel\.auditEmpty/)).toBeNull()
  })

  it('truly empty stays empty, and only after a successful reply', async () => {
    await renderResponse({ entries: [], total_matching: 0 })
    expect(await screen.findByText(/agentPanel\.auditEmpty/)).toBeTruthy()
    expect(screen.queryByTestId('audit-error')).toBeNull()
  })

  it('the status code comes only from a message that carries one', () => {
    expect(auditErrorCode('API 500: Internal Server Error')).toBe('500')
    expect(auditErrorCode('network down')).toBe('')
    expect(auditErrorCode('')).toBe('')
  })
})

describe('N1.7: hanging has to read differently from success', () => {
  it('the refresh button carries the loading state while the list stays', async () => {
    let release: (v: AuditReply) => void = () => {}
    ;(getAudit as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ entries: [entry({})], total_matching: 7 })
      .mockImplementationOnce(
        () =>
          new Promise((res) => {
            release = res as (v: AuditReply) => void
          }),
      )
    render(<AuditTab />)
    await screen.findByTestId('audit-entry-row')
    fireEvent.click(screen.getByTestId('audit-refresh'))
    expect(screen.getByTestId('audit-refresh').getAttribute('aria-busy')).toBe('true')
    expect(screen.getByTestId('audit-refresh-spinner')).toBeTruthy()
    expect(screen.getAllByTestId('audit-entry-row')).toHaveLength(1)
    release({ entries: [entry({}), entry({ ts: '2026-10-05T09:00:00+00:00' })], total_matching: 7 })
    await screen.findAllByTestId('audit-entry-duration')
    await vi.waitFor(() =>
      expect(screen.getByTestId('audit-refresh').getAttribute('aria-busy')).toBe('false'),
    )
  })

  it('the updated-at line appears only after a successful request', async () => {
    await renderResponse({ entries: [entry({})] })
    const stamp = await screen.findByTestId('audit-updated')
    expect(stamp.textContent).toContain('agentPanel.auditUpdated')
    expect(stamp.textContent).toMatch(/time=\d{2}:\d{2}:\d{2}/)
  })
})

describe('N1.8: one column, one number format', () => {
  it('both branches run through the same localized formatting', () => {
    expect(auditDuration(942.6, 'de')).toBe('942,6 ms')
    expect(auditDuration(942.6, 'en')).toBe('942.6 ms')
    expect(auditDuration(1234, 'de')).toBe('1,2 s')
    expect(auditDuration(1234, 'en')).toBe('1.2 s')
    expect(auditDuration(0, 'de')).toBe('0 ms')
    expect(auditDuration(Number.NaN, 'de')).toBe('')
  })

  it('the row applies the same comma rule as the header', async () => {
    await renderResponse({
      entries: [entry({ duration_ms: 942.6 }), entry({ duration_ms: 1234 })],
    })
    const durs = await screen.findAllByTestId('audit-entry-duration')
    expect(durs.map((d) => d.textContent)).toEqual(['942,6 ms', '1,2 s'])
  })
})
