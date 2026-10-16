/**
 * G2 — the fleet panel has to make one distinction that no other surface makes: a run that
 * waits on a person, a run that is broken, and a run that is simply working are three
 * different things, and every registry in the product calls the first two "running".
 *
 * The cases are written against those three states rather than against the markup: the
 * failure they guard against is one state wearing another's face — a run waiting for an
 * answer rendered as if it were busy, or a row that needs a person pushed under four that
 * do not.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { FleetRun } from '@/lib/api'
import FleetPanel from './FleetPanel'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

function run(over: Partial<FleetRun> = {}): FleetRun {
  return {
    run_id: 'workspace:abcd1234',
    kind: 'workspace',
    agent: 'agent-a',
    task: 'ws/agent-a-abcd1234',
    workspace_id: 'abcd1234',
    path: '/managed/abcd1234',
    state: 'running',
    needs_you: false,
    running_for_seconds: 90,
    last_event: { kind: 'none', text: '', op: '', age_seconds: null },
    ...over,
  }
}

describe('the fleet board', () => {
  it('says what each state is, in words a reader acts on', () => {
    render(
      <FleetPanel
        runs={[
          run({
            run_id: 'session:sess-1',
            kind: 'session',
            agent: 'sess-1',
            workspace_id: '',
            path: '',
            state: 'waiting_on_human',
            needs_you: true,
            last_event: { kind: 'awaiting', text: 'run_shell', op: '', age_seconds: 30 },
          }),
          run({ state: 'running' }),
          run({ run_id: 'agent:x', kind: 'agent', state: 'blocked', needs_you: true }),
          run({ run_id: 'agent:y', kind: 'agent', state: 'done' }),
        ]}
      />,
    )
    expect(screen.getByTestId('fleet-run-session:sess-1').textContent).toContain(
      'workspaces.runState.waitingOnHuman',
    )
    expect(screen.getByTestId('fleet-run-workspace:abcd1234').textContent).toContain(
      'workspaces.runState.running',
    )
    expect(screen.getByTestId('fleet-run-agent:x').textContent).toContain(
      'workspaces.runState.blocked',
    )
    expect(screen.getByTestId('fleet-run-agent:y').textContent).toContain(
      'workspaces.runState.done',
    )
  })

  it('marks the run that waits on a person, and only that one', () => {
    render(
      <FleetPanel
        runs={[
          run({
            run_id: 'session:sess-1',
            kind: 'session',
            state: 'waiting_on_human',
            needs_you: true,
            last_event: { kind: 'awaiting', text: 'run_shell', op: '', age_seconds: 30 },
          }),
          run({ state: 'running' }),
        ]}
      />,
    )
    const asked = screen.getByTestId('fleet-needs-you-session:sess-1')
    expect(asked.textContent).toBe('workspaces.fleet.answerNeeded')
    expect(screen.queryByTestId('fleet-needs-you-workspace:abcd1234')).toBeNull()
    // The approval a run is stopped on is named, not implied by the state alone.
    expect(screen.getByTestId('fleet-run-session:sess-1').textContent).toContain('run_shell')
  })

  it('tells a stuck run what it needs apart from one that needs an answer', () => {
    render(
      <FleetPanel
        runs={[
          run({
            run_id: 'session:sess-1',
            kind: 'session',
            state: 'waiting_on_human',
            needs_you: true,
          }),
          run({ run_id: 'agent:x', kind: 'agent', state: 'blocked', needs_you: true }),
        ]}
      />,
    )
    expect(screen.getByTestId('fleet-needs-you-session:sess-1').textContent).toBe(
      'workspaces.fleet.answerNeeded',
    )
    expect(screen.getByTestId('fleet-needs-you-agent:x').textContent).toBe(
      'workspaces.fleet.needsRestart',
    )
  })

  it('counts what is on the board and what needs the reader', () => {
    render(
      <FleetPanel
        runs={[
          run({ run_id: 'session:s', kind: 'session', state: 'waiting_on_human', needs_you: true }),
          run({ run_id: 'agent:x', kind: 'agent', state: 'blocked', needs_you: true }),
          run({ state: 'running' }),
        ]}
      />,
    )
    const summary = screen.getByTestId('fleet-summary').textContent ?? ''
    expect(summary).toContain('workspaces.fleet.count')
    expect(summary).toContain('"count":3')
    expect(summary).toContain('workspaces.fleet.needsYou')
    expect(summary).toContain('"count":2')
  })

  it('reads the last thing a run touched, whether file or tool', () => {
    render(
      <FleetPanel
        runs={[
          run({
            last_event: { kind: 'file', text: 'app/src/x.tsx', op: 'modify', age_seconds: 12 },
          }),
          run({
            run_id: 'agent:x',
            kind: 'agent',
            workspace_id: '',
            path: '',
            last_event: { kind: 'tool', text: 'web_search', op: '', age_seconds: 3 },
          }),
        ]}
      />,
    )
    const first = screen.getByTestId('fleet-run-workspace:abcd1234').textContent ?? ''
    expect(first).toContain('app/src/x.tsx')
    expect(first).toContain('workspaces.fleet.touched')
    const second = screen.getByTestId('fleet-run-agent:x').textContent ?? ''
    expect(second).toContain('web_search')
    expect(second).toContain('workspaces.fleet.usedTool')
    // A run with no checkout says so rather than leaving a hole.
    expect(second).toContain('workspaces.fleet.noCheckout')
  })

  it('says a run has touched nothing rather than claiming an empty path', () => {
    render(<FleetPanel runs={[run()]} />)
    expect(screen.getByTestId('fleet-run-workspace:abcd1234').textContent).toContain(
      'workspaces.fleet.touchedNothing',
    )
  })

  it('puts each state in its own tense: waiting, running, ran, finished', () => {
    render(
      <FleetPanel
        runs={[
          run({
            run_id: 'session:s',
            kind: 'session',
            state: 'waiting_on_human',
            needs_you: true,
            running_for_seconds: 45,
          }),
          run({ running_for_seconds: 90 }),
          run({
            run_id: 'agent:x',
            kind: 'agent',
            state: 'blocked',
            needs_you: true,
            running_for_seconds: 30,
          }),
          run({ run_id: 'agent:y', kind: 'agent', state: 'done', running_for_seconds: 12 }),
        ]}
      />,
    )
    expect(screen.getByTestId('fleet-run-session:s').textContent).toContain(
      'workspaces.fleet.waitedFor',
    )
    expect(screen.getByTestId('fleet-run-workspace:abcd1234').textContent).toContain(
      'workspaces.fleet.runningFor',
    )
    expect(screen.getByTestId('fleet-run-agent:x').textContent).toContain('workspaces.fleet.ranFor')
    expect(screen.getByTestId('fleet-run-agent:y').textContent).toContain(
      'workspaces.fleet.finishedIn',
    )
  })

  it('keeps the order the board sent, and lets a checkout be picked', () => {
    const picked: string[] = []
    render(
      <FleetPanel
        runs={[
          run({ run_id: 'session:s', kind: 'session', state: 'waiting_on_human', needs_you: true }),
          run({ state: 'done' }),
        ]}
        onSelect={(id) => picked.push(id)}
      />,
    )
    const rows = screen.getAllByTestId(/^fleet-run-/)
    expect(rows[0]!.getAttribute('data-testid')).toBe('fleet-run-session:s')
    expect(rows[1]!.getAttribute('data-testid')).toBe('fleet-run-workspace:abcd1234')
    // A row that owns a checkout is a way into it; a wait owns none and is not one.
    rows[1]!.click()
    expect(picked).toEqual(['abcd1234'])
  })

  it('shows nothing at all when no run is live', () => {
    const { container } = render(<FleetPanel runs={[]} />)
    expect(container.firstChild).toBeNull()
  })
})
