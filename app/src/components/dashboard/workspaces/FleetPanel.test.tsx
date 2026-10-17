/**
 * G2 — the fleet panel has to make one distinction that no other surface makes: a run that
 * waits on a person, a run that is broken, and a run that is simply working are three
 * different things, and every registry in the product calls the first two "running".
 *
 * The cases are written against those three states rather than against the markup: the
 * failure they guard against is one state wearing another's face — a run waiting for an
 * answer rendered as if it were busy, or a row that needs a person pushed under four that
 * do not.
 *
 * A row also has to answer why it is not moving without inventing a cause. `blocked` carries
 * no reason in the payload, so the generic sentence is the honest one and the last tool is
 * named only when the event names it.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ChangeSet, FleetRun, Workspace } from '@/lib/api'
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

function workspace(over: Partial<Workspace> = {}): Workspace {
  return {
    id: 'abcd1234',
    path: '/managed/abcd1234',
    branch: 'ws/agent-a-abcd1234',
    state: 'ready',
    owner: 'agent-a',
    created_at: new Date(Date.now() - 3 * 3_600_000).toISOString(),
    ...over,
  }
}

function changeSet(over: Partial<ChangeSet> = {}): ChangeSet {
  return {
    id: 'cs-1',
    workspace_id: 'abcd1234',
    summary: 'The page the run asked for',
    files: [
      { path: 'app/src/a.tsx', op: 'modify', diff_sha: 'sha256:aa' },
      { path: 'app/src/b.ts', op: 'create', diff_sha: 'sha256:bb' },
    ],
    provenance: { session_id: 'sess-1', agent_id: 'agent-a', why: 'because it had to' },
    state: 'draft',
    ...over,
  }
}

const show = (ui: React.ReactNode) =>
  render(<MemoryRouter initialEntries={['/workspaces']}>{ui}</MemoryRouter>)

describe('the fleet board', () => {
  it('says what each state is, in words a reader acts on', () => {
    show(
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
    show(
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
    show(
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

  it('puts the runs that need a person first and lets every one explain itself', () => {
    // The order `core.fleet.build` sends: waiting, blocked, running, done.
    const runs = [
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
      run({
        run_id: 'agent:blocked-1',
        kind: 'agent',
        agent: 'agent-blocked',
        workspace_id: '',
        path: '',
        state: 'blocked',
        needs_you: true,
      }),
      run({ state: 'running' }),
      run({ run_id: 'agent:done-1', kind: 'agent', agent: 'agent-done', state: 'done' }),
    ]
    show(<FleetPanel runs={runs} />)

    const rows = screen.getAllByTestId(/^fleet-run-/)
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'fleet-run-session:sess-1',
      'fleet-run-agent:blocked-1',
      'fleet-run-workspace:abcd1234',
      'fleet-run-agent:done-1',
    ])

    for (const r of runs) {
      const row = screen.getByTestId(`fleet-run-${r.run_id}`)
      // No row is only a badge: every row names the agent behind it.
      expect(row.textContent).toContain(r.agent)
    }

    for (const id of ['session:sess-1', 'agent:blocked-1']) {
      expect(screen.getByTestId(`fleet-why-${id}`).textContent).not.toBe('')
      expect(screen.getByTestId(`fleet-action-${id}`)).toBeTruthy()
    }
    // A row that is merely working or finished is not asked to explain a problem.
    expect(screen.queryByTestId('fleet-why-workspace:abcd1234')).toBeNull()
    expect(screen.queryByTestId('fleet-action-workspace:abcd1234')).toBeNull()
    expect(screen.queryByTestId('fleet-why-agent:done-1')).toBeNull()
  })

  it('opens a wait at its task and a stuck run at its checkout', () => {
    const picked: string[] = []
    show(
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
          }),
          run({
            run_id: 'agent:blocked-1',
            kind: 'agent',
            agent: 'agent-blocked',
            state: 'blocked',
            needs_you: true,
          }),
        ]}
        onSelect={(id) => picked.push(id)}
      />,
    )
    expect(screen.getByTestId('fleet-action-session:sess-1').getAttribute('href')).toBe(
      '/chat?session=sess-1&replay=1',
    )
    fireEvent.click(screen.getByTestId('fleet-action-agent:blocked-1'))
    expect(picked).toEqual(['abcd1234'])
  })

  it('names the last tool on a stuck run and invents no reason when there is none', () => {
    show(
      <FleetPanel
        runs={[
          run({
            run_id: 'agent:tool-1',
            kind: 'agent',
            state: 'blocked',
            needs_you: true,
            last_event: { kind: 'tool', text: 'execute_code', op: '', age_seconds: 5 },
          }),
          run({ run_id: 'agent:bare-1', kind: 'agent', state: 'blocked', needs_you: true }),
        ]}
      />,
    )
    const named = screen.getByTestId('fleet-why-agent:tool-1').textContent ?? ''
    expect(named).toContain('workspaces.fleet.whyBlockedTool')
    expect(named).toContain('execute_code')
    expect(screen.getByTestId('fleet-why-agent:bare-1').textContent).toBe(
      'workspaces.fleet.whyBlocked',
    )
  })

  it('counts what is on the board and what needs the reader', () => {
    show(
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
    show(
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
    show(<FleetPanel runs={[run()]} />)
    expect(screen.getByTestId('fleet-run-workspace:abcd1234').textContent).toContain(
      'workspaces.fleet.touchedNothing',
    )
  })

  it('labels both clocks: the run and the checkout it works in', () => {
    show(<FleetPanel runs={[run({ running_for_seconds: 720 })]} workspaces={[workspace()]} />)
    const text = screen.getByTestId('fleet-run-workspace:abcd1234').textContent ?? ''
    expect(text).toContain('workspaces.fleet.runClock')
    expect(text).toContain('"duration":"12m"')
    expect(text).toContain('workspaces.fleet.checkoutClock')
    expect(text).toContain('workspaces.age.hours')
    expect(text).toContain('\\"n\\":3')
  })

  it('summarizes the latest change set by operation and names approval', () => {
    show(
      <FleetPanel
        runs={[run()]}
        workspaces={[workspace()]}
        changeSets={{ abcd1234: [changeSet()] }}
      />,
    )
    const text = screen.getByTestId('fleet-changes-workspace:abcd1234').textContent ?? ''
    expect(text).toContain('workspaces.fleet.latestChange')
    expect(text).toContain('workspaces.files')
    expect(text).toContain('"count":2')
    expect(text).toContain('workspaces.opCount')
    expect(text).toContain('workspaces.op.modify')
    expect(text).toContain('workspaces.op.create')
    expect(text).toContain('workspaces.fleet.approvalNeeded')
  })

  it('keeps the order the board sent, and lets a checkout be picked', () => {
    const picked: string[] = []
    show(
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
    fireEvent.click(screen.getByTestId('fleet-select-workspace:abcd1234'))
    expect(picked).toEqual(['abcd1234'])
  })

  it('shows nothing at all when no run is live', () => {
    const { container } = render(
      <MemoryRouter>
        <FleetPanel runs={[]} />
      </MemoryRouter>,
    )
    expect(container.firstChild).toBeNull()
  })
})
