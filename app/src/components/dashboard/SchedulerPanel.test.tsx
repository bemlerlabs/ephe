import { beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SchedulerPanel, { SchedulerMobilePill } from './SchedulerPanel'
import type { ScheduleJob, ScheduleResult } from '@/lib/api'

// P2-B: mock the keep-awake hook (the real hook pulls in chatStore/i18n; only the
// panel logic is meant to be tested here — wake-lock path: useKeepAwake.test)
const ka = vi.hoisted(() => ({
  state: {
    supported: true,
    active: false,
    error: false,
    via: 'wakeLock' as 'wakeLock' | 'tauri' | null,
  },
}))
vi.mock('@/hooks/useKeepAwake', () => ({
  useKeepAwake: () => ka.state,
}))

// R40: the run history is fed through the API (presets stay empty so the
// template/job assertions of the older tests remain stable).
const api = vi.hoisted(() => ({
  presets: [] as Array<{ id: string; title: string; task: string; cron: string }>,
  results: [] as ScheduleResult[],
}))
vi.mock('@/lib/api', () => ({
  getSchedulePresets: vi.fn(async () => ({ presets: api.presets })),
  getScheduleResults: vi.fn(async () => ({ results: api.results })),
  runScheduleJob: vi.fn(async () => api.results[0]),
}))

// i18n mock (SchedulerPanel uses useTranslation)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      const map: Record<string, string> = {
        'scheduler.title': 'Wiederkehrende Aufgaben',
        'scheduler.taskPlaceholder': 'Aufgabe (natürliche Sprache)',
        'scheduler.cronPlaceholder': 'Cron (z.B. 0 8 * * *)',
        'scheduler.delayPlaceholder': 'Verzug min (Einmalig)',
        'scheduler.maxRunsPlaceholder': 'Max Läufe (optional)',
        'scheduler.createJob': 'Job anlegen',
        'scheduler.deleteJob': 'Job {id} löschen',
        'scheduler.history': 'Run-History',
        'scheduler.runNow': 'Jetzt ausführen',
        'scheduler.runFinished': 'Automation fertig',
        'scheduler.runFailed': 'Automation fehlgeschlagen',
        'scheduler.open': 'Geplante Aufgaben ansehen',
        'automation.preset.daily-standup.title': 'Täglicher Standup',
        'automation.empty': 'Noch keine geplanten Aufgaben.', // language-gate: ignore
      }
      let s = map[key] ?? opts?.defaultValue ?? key
      if (opts) s = s.replace('{id}', opts.id ?? '')
      return s
    },
  }),
}))

function makeJob(id: string, task: string, cron: string): ScheduleJob {
  return { id, task, cron, next_run: '2026-08-09 08:00' }
}

describe('SchedulerPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    ka.state = { supported: true, active: false, error: false, via: 'wakeLock' }
    api.presets = []
    api.results = []
  })
  it('collapses/expands via the header toggle (persisted state respected)', () => {
    // R19: the default is expanded (presets/history visible); '1' = the user collapsed it
    const { container } = render(<SchedulerPanel jobs={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByPlaceholderText('Aufgabe (natürliche Sprache)')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Wiederkehrende Aufgaben/ }))
    expect(screen.queryByPlaceholderText('Aufgabe (natürliche Sprache)')).toBeNull()
    expect(container.querySelector('[aria-expanded="false"]')).toBeTruthy()
    expect(localStorage.getItem('ephe.scheduler.collapsed')).toBe('1')
  })

  // I5-4: the preset chips come from the server (core/scheduler.py) and are English
  // there. In the German interface they stood untranslated next to German cards — so
  // the chip has to ask for a locale key instead of printing the server text;
  // without a key the server text stays as the honest fallback.
  it('labels preset chips from the locale, falling back to the server title', async () => {
    api.presets = [
      { id: 'daily-standup', title: 'Daily Standup Summary', task: 't1', cron: '0 8 * * 1-5' },
      { id: 'unknown-preset', title: 'Some Server Title', task: 't2', cron: '0 9 * * *' },
    ]
    render(<SchedulerPanel jobs={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Täglicher Standup')).toBeTruthy())
    expect(screen.getByText('Some Server Title')).toBeTruthy()
    expect(screen.queryByText('Daily Standup Summary')).toBeNull()
  })

  it('explains the create form (cron vs. delay vs. max runs)', () => {
    render(<SchedulerPanel jobs={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('scheduler.formHint')).toBeTruthy()
  })

  it('fires onCreate with task and cron', () => {
    const onCreate = vi.fn()
    render(<SchedulerPanel jobs={[]} onCreate={onCreate} onDelete={vi.fn()} />)
    // R19: the panel starts expanded — no expand() needed any more
    fireEvent.change(screen.getByPlaceholderText('Aufgabe (natürliche Sprache)'), {
      target: { value: 'Tägliche Zusammenfassung' },
    })
    fireEvent.change(screen.getByPlaceholderText('Cron (z.B. 0 8 * * *)'), {
      target: { value: '0 8 * * *' },
    })
    fireEvent.click(screen.getByTitle('Job anlegen'))
    expect(onCreate).toHaveBeenCalledWith(
      'Tägliche Zusammenfassung',
      '0 8 * * *',
      undefined,
      undefined,
    )
  })

  it('fires onCreate with delay and max-runs for relative one-shots (J4)', () => {
    const onCreate = vi.fn()
    render(<SchedulerPanel jobs={[]} onCreate={onCreate} onDelete={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('Aufgabe (natürliche Sprache)'), {
      target: { value: 'Einmaliger Lauf' },
    })
    fireEvent.change(screen.getByPlaceholderText('Verzug min (Einmalig)'), {
      target: { value: '5' },
    })
    fireEvent.change(screen.getByPlaceholderText('Max Läufe (optional)'), {
      target: { value: '2' },
    })
    fireEvent.click(screen.getByTitle('Job anlegen'))
    expect(onCreate).toHaveBeenCalledWith('Einmaliger Lauf', '', 5, 2)
  })

  it('lists scheduled jobs (expanded, jobs > 0)', () => {
    render(
      <SchedulerPanel
        jobs={[makeJob('j1', 'Täglich', '0 8 * * *')]}
        onCreate={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    // jobs.length > 0 → starts expanded
    expect(screen.getByText('Täglich')).toBeTruthy()
    expect(screen.getByTitle('Job j1 löschen')).toBeTruthy()
  })

  it('fires onDelete with the job id', () => {
    const onDelete = vi.fn()
    render(
      <SchedulerPanel
        jobs={[makeJob('j1', 'Täglich', '0 8 * * *')]}
        onCreate={vi.fn()}
        onDelete={onDelete}
      />,
    )
    fireEvent.click(screen.getByTitle('Job j1 löschen'))
    expect(onDelete).toHaveBeenCalledWith('j1')
  })

  // ── P2-B: template cards ──────────────────────────────────────────────────

  it('template click pre-fills the form (prompt + cadence cron) and create fires with preset fields', () => {
    const onCreate = vi.fn()
    render(<SchedulerPanel jobs={[]} onCreate={onCreate} onDelete={vi.fn()} />)
    for (let i = 0; i < 4; i++) {
      expect(screen.getByTestId(`automation-template-${i}`)).toBeTruthy()
    }
    fireEvent.click(screen.getByTestId('automation-template-0'))
    const taskText = (
      screen.getByPlaceholderText('Aufgabe (natürliche Sprache)') as HTMLInputElement
    ).value
    expect(taskText.length).toBeGreaterThan(0) // prompt pre-filled
    expect((screen.getByPlaceholderText('Cron (z.B. 0 8 * * *)') as HTMLInputElement).value).toBe(
      '0 9 * * 1-5',
    ) // weekdays 09:00
    // The form's confirmation pattern: the create button fires onCreate
    fireEvent.click(screen.getByTitle('Job anlegen'))
    expect(onCreate).toHaveBeenCalledWith(taskText, '0 9 * * 1-5', undefined, undefined)
    // After creating, the form is emptied again
    expect(
      (screen.getByPlaceholderText('Aufgabe (natürliche Sprache)') as HTMLInputElement).value,
    ).toBe('')
    expect((screen.getByPlaceholderText('Cron (z.B. 0 8 * * *)') as HTMLInputElement).value).toBe(
      '',
    )
  })

  it('shows the empty-state hint when no jobs exist (parity: automations surface)', () => {
    render(<SchedulerPanel jobs={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByTestId('automation-empty').textContent).toContain(
      'Noch keine geplanten Aufgaben.',
    )
  })

  // ── P2-B: keep-awake toggle ───────────────────────────────────────────────

  it('keep-awake toggle persists to localStorage ephe_keep_awake', () => {
    render(<SchedulerPanel jobs={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    const toggle = screen
      .getByTestId('automation-keep-awake')
      .querySelector('[role="switch"]') as HTMLButtonElement
    expect(toggle).toBeTruthy()
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(localStorage.getItem('ephe_keep_awake')).toBe('1')
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    expect(localStorage.getItem('ephe_keep_awake')).toBe('0')
  })

  it('keep-awake toggle is disabled with an honest hint when no mechanism exists', () => {
    ka.state = { supported: false, active: false, error: false, via: null }
    render(<SchedulerPanel jobs={[]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    const toggle = screen
      .getByTestId('automation-keep-awake')
      .querySelector('[role="switch"]') as HTMLButtonElement
    expect((toggle as HTMLButtonElement).disabled).toBe(true)
    // a hint instead of a dead toggle
    expect(screen.getByTestId('automation-keep-awake-hint')).toBeTruthy()
    fireEvent.click(toggle)
    expect(localStorage.getItem('ephe_keep_awake')).toBeNull()
  })

  // ── R40: structured run history (full detail instead of a truncated row) ──

  function makeResult(partial: Partial<ScheduleResult>): ScheduleResult {
    return {
      job_id: 'j1',
      task: 'Morgen-Brief',
      executed_at: '2026-10-02T09:00:00.123456',
      result: '',
      error: null,
      ...partial,
    }
  }

  const LONG_OK = 'Zeile 1\nZeile 2: die vollstaendige Automation-Ausgabe mit Details'
  const LONG_ERR = 'Traceback (most recent call last)\nTimeoutError: Ollama nicht erreichbar'

  it('run-history rows start collapsed and expand to the full result with its status', async () => {
    api.results = [makeResult({ result: LONG_OK })]
    render(
      <SchedulerPanel
        jobs={[makeJob('j1', 'Morgen-Brief', '0 9 * * 1-5')]}
        onCreate={vi.fn()}
        onDelete={vi.fn()}
      />,
    )

    const row = await screen.findByTestId('scheduler-run-row-0')
    expect(screen.queryByTestId('scheduler-run-detail-0')).toBeNull()
    expect(row.textContent).toContain('Morgen-Brief')

    fireEvent.click(row)
    const detail = await screen.findByTestId('scheduler-run-detail-0')
    expect(detail.textContent).toContain('Zeile 2')
    expect(detail.textContent).toContain('Automation fertig')
    // the exact execution time stays readable (no .slice truncation)
    expect(detail.textContent).toContain('2026-10-02T09:00:00.123456')
    expect(row.getAttribute('aria-expanded')).toBe('true')

    fireEvent.click(row)
    expect(screen.queryByTestId('scheduler-run-detail-0')).toBeNull()
    expect(row.getAttribute('aria-expanded')).toBe('false')
  })

  it('keeps an expansion attached to its run when a new result is polled in', async () => {
    const jobs = [makeJob('j1', 'Morgen-Brief', '0 9 * * 1-5')]
    const older = makeResult({
      job_id: 'j1',
      executed_at: '2026-10-01T09:00:00',
      result: 'aelter Lauf',
    })
    api.results = [
      makeResult({ job_id: 'j0', executed_at: '2026-10-02T08:00:00', result: 'oberster' }),
      older,
    ]
    const { rerender } = render(
      <SchedulerPanel jobs={jobs} onCreate={vi.fn()} onDelete={vi.fn()} />,
    )
    const secondRow = await screen.findByTestId('scheduler-run-row-1')
    fireEvent.click(secondRow)
    expect((await screen.findByTestId('scheduler-run-detail-1')).textContent).toContain(
      'aelter Lauf',
    )

    // A new run on top → the rows shift. The run that is open stays open (run key,
    // not index); the new one stays collapsed.
    api.results = [
      makeResult({ job_id: 'j9', executed_at: '2026-10-02T09:30:00', result: 'neuer Lauf' }),
      ...api.results,
    ]
    rerender(<SchedulerPanel jobs={[...jobs]} onCreate={vi.fn()} onDelete={vi.fn()} />)
    await vi.waitFor(() =>
      expect(screen.getByTestId('scheduler-run-detail-2').textContent).toContain('aelter Lauf'),
    )
    expect(screen.getByTestId('scheduler-run-row-2').getAttribute('aria-expanded')).toBe('true')
    expect(screen.queryByTestId('scheduler-run-detail-0')).toBeNull()
    expect(screen.getByTestId('scheduler-run-row-1').getAttribute('aria-expanded')).toBe('false')
  })

  it('failure rows surface the full error, not a truncated line', async () => {
    api.results = [makeResult({ result: '', error: LONG_ERR })]
    render(
      <SchedulerPanel
        jobs={[makeJob('j1', 'Morgen-Brief', '0 9 * * 1-5')]}
        onCreate={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    const row = await screen.findByTestId('scheduler-run-row-0')
    fireEvent.click(row)
    const detail = await screen.findByTestId('scheduler-run-detail-0')
    expect(detail.textContent).toContain('TimeoutError: Ollama nicht erreichbar')
    expect(detail.textContent).toContain('Automation fehlgeschlagen')
  })

  // ── R40: mobile pill (compact surface for scheduled tasks) ────────────────

  it('mobile pill shows the job count and soonest next run and opens the cron surface', () => {
    const onOpen = vi.fn()
    render(
      <SchedulerMobilePill
        jobs={[
          { ...makeJob('j1', 'Morgen-Brief', '0 9 * * 1-5'), next_run: '2026-12-01 08:00' },
          makeJob('j2', 'Wochen-Report', '0 16 * * 5'),
        ]}
        onOpen={onOpen}
      />,
    )
    const pill = screen.getByTestId('scheduler-mobile-pill')
    // parity DD-10: counterpart to the md:block banner, does not disturb desktop
    expect(String(pill.className)).toMatch(/(^|\s)md:hidden(\s|$)/)
    expect(pill.textContent).toContain('2')
    // the next run = the earliest one, not the first in the list
    expect(pill.textContent).toContain('2026-08-09 08:00')
    expect(pill.textContent).not.toContain('2026-12-01 08:00')
    expect(pill.getAttribute('aria-label')).toBe('Geplante Aufgaben ansehen')
    fireEvent.click(pill)
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('mobile pill degrades gracefully when no job has a next run', () => {
    const onOpen = vi.fn()
    render(
      <SchedulerMobilePill
        jobs={[{ id: 'j1', task: 'Ohne Lauf', cron: '0 8 * * *' }]}
        onOpen={onOpen}
      />,
    )
    const pill = screen.getByTestId('scheduler-mobile-pill')
    expect(pill.textContent).toContain('1')
    // without next_run (e.g. a scheduled one-shot) the pill shows only the counter
    expect(pill.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/)
  })
})
