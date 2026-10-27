/**
 * QD-005 — the companion's co-pilot brain, proven before it exists.
 *
 * `companionCopilot.ts` is the deterministic classifier between the five Ephe
 * surface targets and the three companion modes. Its one security job is the
 * shell-command allowlist: a command that chains, writes, reaches the network or
 * leaves the workspace must never earn `auto_act`. These tests are written
 * first; the module follows.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  COUNTDOWN_MS,
  RECEIPT_CAP,
  bindEscapeCancel,
  classifyAsk,
  classifyShellCommand,
  CopilotCountdown,
  findCopilotTarget,
  pushReceipt,
  shouldCompact,
  shouldOpenReview,
  shellCommandOf,
  type CopilotSnapshot,
} from './companionCopilot'

function snap(overrides: Partial<CopilotSnapshot> = {}): CopilotSnapshot {
  return {
    waitingTool: null,
    ask: null,
    runState: 'ready',
    contextPercent: null,
    hasCompact: false,
    compactedThisSession: false,
    turnJustFinished: false,
    newArtifacts: 0,
    newEdits: 0,
    toolError: false,
    repairVisible: false,
    ...overrides,
  }
}

function waitingTool(command: string) {
  return { name: 'execute_code', args: { command }, description: 'token-1' }
}

describe('classifyShellCommand — the allowlist is the whole security boundary', () => {
  it.each([
    'pytest',
    'pytest tests/test_a.py',
    'python -m pytest',
    'python -m pytest -q tests/',
    'python3 -m pytest',
    'npm test',
    'npm run lint',
    'npm run build',
    'npx vitest',
    'npx vitest --run',
    'cargo check',
    'cargo test',
    'cargo clippy --all-targets -- -D warnings',
    'git status',
    'git diff',
    'git log --oneline -3',
    'ruff check',
  ])('reads %j as a safe single check', (command) => {
    expect(classifyShellCommand(command)).toBe('auto_act')
  })

  it.each([
    'rm -rf /tmp/x',
    'rm',
    'RM -rf x',
    'pytest && rm -rf .',
    'pytest; id',
    'npm run lint && npm test',
    'git push origin main',
    'git reset --hard',
    'git clean -fd',
    'git checkout -- .',
    'curl -s https://example.invalid',
    'wget https://example.invalid',
    'ssh host',
    'scp a b',
    'sudo npm test',
    'su -',
    'mv a b',
    'chmod 777 x',
    'chown u x',
    'kill -9 1',
    'pkill node',
    'dd if=/dev/zero of=x',
    'echo $(id)',
    'echo `id`',
    'pytest > /tmp/x',
    'cat a | less',
    'pytest ../tests',
    'cat ~/.ephe/engine.key',
    'ls .env',
    'ls .env.example',
    'pytest\nls',
    '',
    'pytest;',
    'echo hello',
  ])('refuses %j, chained or out of the workspace', (command) => {
    expect(classifyShellCommand(command)).toBe('warn_only')
  })

  it('reads the command out of the tool args, command first', () => {
    expect(shellCommandOf({ name: 'execute_code', args: { command: 'pytest' } })).toBe('pytest')
    expect(shellCommandOf({ name: 'run_shell', args: { cmd: 'git status' } })).toBe('git status')
    expect(shellCommandOf({ name: 'execute_code', args: { code: 'x' } })).toBe('')
  })
})

describe('classifyAsk — one clear recommendation answers itself, nothing else does', () => {
  it('a recommendation that is one of the options is safe to answer', () => {
    expect(classifyAsk('Continue', ['Stop', 'Continue'])).toBe('auto_act')
  })

  it.each([
    [undefined, ['Stop', 'Continue']],
    ['Continue', []],
    ['Maybe', ['Stop', 'Continue']],
    ['', ['Stop', 'Continue']],
  ])('a %j recommendation over %j options waits for the user', (rec, options) => {
    expect(classifyAsk(rec, options as string[])).toBe('warn_only')
  })
})

describe('shouldCompact — once per session, at the threshold, after the turn', () => {
  it('fires exactly at the finished 90% case', () => {
    expect(
      shouldCompact({
        runState: 'done',
        contextPercent: 90,
        hasCompact: true,
        compactedThisSession: false,
      }),
    ).toBe(true)
  })

  it.each([
    { runState: 'working' },
    { contextPercent: 89 },
    { runState: 'ready', contextPercent: null },
    { hasCompact: false },
    { compactedThisSession: true },
  ])('stays quiet for %j', (overrides) => {
    expect(
      shouldCompact({
        runState: 'done',
        contextPercent: 95,
        hasCompact: true,
        compactedThisSession: false,
        ...overrides,
      }),
    ).toBe(false)
  })
})

describe('shouldOpenReview — a finished turn that produced something new', () => {
  it('opens the review for edits or artifacts of the turn that just ended', () => {
    expect(shouldOpenReview({ turnJustFinished: true, newArtifacts: 1, newEdits: 0 })).toBe(true)
    expect(shouldOpenReview({ turnJustFinished: true, newArtifacts: 0, newEdits: 2 })).toBe(true)
  })

  it('stays quiet without fresh output', () => {
    expect(shouldOpenReview({ turnJustFinished: false, newArtifacts: 1, newEdits: 0 })).toBe(false)
    expect(shouldOpenReview({ turnJustFinished: true, newArtifacts: 0, newEdits: 0 })).toBe(false)
  })
})

describe('findCopilotTarget — the five targets through the three modes', () => {
  it('perch never crawls, whatever the surface shows', () => {
    expect(findCopilotTarget(snap({ waitingTool: waitingTool('pytest') }), 'perch')).toBeNull()
    expect(findCopilotTarget(snap({ ask: { recommendation: 'a', options: ['a'] } }), 'perch')).toBeNull()
    expect(findCopilotTarget(snap({ contextPercent: 95, runState: 'done', hasCompact: true }), 'perch')).toBeNull()
  })

  it('copilot approves a safe waiting check and names the command', () => {
    const finding = findCopilotTarget(snap({ waitingTool: waitingTool('pytest -q') }), 'copilot')
    expect(finding).toMatchObject({
      target: 'tool_approval',
      verdict: 'auto_act',
      actionKey: 'copilot.action.approve',
      actionParam: 'pytest -q',
    })
  })

  it('a risky or chained command is warn_only in copilot mode, never approved', () => {
    for (const command of ['rm -rf .', 'pytest && rm', 'git push', 'curl x']) {
      const finding = findCopilotTarget(snap({ waitingTool: waitingTool(command) }), 'copilot')
      expect(finding?.verdict).toBe('warn_only')
      expect(finding?.actionKey).toBe('copilot.action.noApprove')
    }
  })

  it('a waiting tool without a command string is warn_only', () => {
    const finding = findCopilotTarget(
      snap({ waitingTool: { name: 'execute_code', args: { code: 'x' }, description: 't' } }),
      'copilot',
    )
    expect(finding?.verdict).toBe('warn_only')
    expect(finding?.reasonKey).toBe('copilot.reason.commandUnreadable')
  })

  it('scout points at the approval dialog but never acts', () => {
    const finding = findCopilotTarget(snap({ waitingTool: waitingTool('pytest') }), 'scout')
    expect(finding).toMatchObject({
      target: 'tool_approval',
      verdict: 'focus',
      actionKey: 'copilot.action.approveYourself',
    })
  })

  it('the waiting approval outranks an open question', () => {
    const finding = findCopilotTarget(
      snap({
        waitingTool: waitingTool('pytest'),
        ask: { recommendation: 'Continue', options: ['Continue'] },
      }),
      'copilot',
    )
    expect(finding?.target).toBe('tool_approval')
  })

  it('copilot answers a question whose recommendation is unambiguous', () => {
    const finding = findCopilotTarget(
      snap({ ask: { recommendation: 'Continue', options: ['Stop', 'Continue'] } }),
      'copilot',
    )
    expect(finding).toMatchObject({
      target: 'ask_user',
      verdict: 'auto_act',
      actionKey: 'copilot.action.answer',
      actionParam: 'Continue',
    })
  })

  it('an open question without a recommendation waits', () => {
    const finding = findCopilotTarget(snap({ ask: { options: ['Stop', 'Continue'] } }), 'copilot')
    expect(finding).toMatchObject({
      target: 'ask_user',
      verdict: 'warn_only',
      actionKey: 'copilot.action.noAnswer',
    })
  })

  it('copilot compacts a session that crossed 90% after the turn', () => {
    const finding = findCopilotTarget(
      snap({ runState: 'done', contextPercent: 92, hasCompact: true }),
      'copilot',
    )
    expect(finding).toMatchObject({
      target: 'context_compact',
      verdict: 'auto_act',
      actionKey: 'copilot.action.compact',
      reasonParam: '92',
    })
  })

  it('a session compacted once this session is left alone', () => {
    const finding = findCopilotTarget(
      snap({ runState: 'done', contextPercent: 92, hasCompact: true, compactedThisSession: true }),
      'copilot',
    )
    expect(finding).toBeNull()
  })

  it('copilot opens the review when the turn produced edits', () => {
    const finding = findCopilotTarget(
      snap({ turnJustFinished: true, newEdits: 1 }),
      'copilot',
    )
    expect(finding).toMatchObject({
      target: 'open_review_or_preview',
      verdict: 'auto_act',
      actionKey: 'copilot.action.openReview',
    })
  })

  it('a tool error or a repair surface yields focus, never an automatic act', () => {
    for (const overrides of [{ toolError: true }, { repairVisible: true }]) {
      const finding = findCopilotTarget(snap(overrides), 'copilot')
      expect(finding).toMatchObject({
        target: 'error_or_setup_repair',
        verdict: 'focus',
        actionKey: 'copilot.action.focusRepair',
      })
    }
  })

  it('an idle surface yields nothing', () => {
    expect(findCopilotTarget(snap(), 'copilot')).toBeNull()
    expect(findCopilotTarget(snap(), 'scout')).toBeNull()
  })
})

describe('pushReceipt — the audit trail stays short and newest-first', () => {
  it('prepends and caps at the receipt limit', () => {
    let list: ReturnType<typeof pushReceipt> = []
    for (let i = 0; i < RECEIPT_CAP + 4; i++) {
      list = pushReceipt(list, {
        at: 1000 + i,
        target: 'tool_approval',
        verdict: 'auto_act',
        actionKey: 'copilot.action.approve',
        actionParam: `act ${i}`,
        reasonKey: 'copilot.reason.safeCheck',
      })
    }
    expect(list).toHaveLength(RECEIPT_CAP)
    expect(list[0]!.actionParam).toBe(`act ${RECEIPT_CAP + 3}`)
    expect(list[RECEIPT_CAP - 1]!.actionParam).toBe('act 4')
  })
})

describe('CopilotCountdown — 2500 ms, one shot, always cancelable', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('runs the action once when the full countdown passes', () => {
    const onComplete = vi.fn()
    const countdown = new CopilotCountdown(COUNTDOWN_MS)
    countdown.start(onComplete)
    vi.advanceTimersByTime(COUNTDOWN_MS - 1)
    expect(onComplete).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('cancel before the deadline means the action never runs', () => {
    const onComplete = vi.fn()
    const countdown = new CopilotCountdown(COUNTDOWN_MS)
    countdown.start(onComplete)
    vi.advanceTimersByTime(1200)
    countdown.cancel()
    vi.advanceTimersByTime(COUNTDOWN_MS)
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('starting a second countdown replaces the first', () => {
    const first = vi.fn()
    const second = vi.fn()
    const countdown = new CopilotCountdown(COUNTDOWN_MS)
    countdown.start(first)
    vi.advanceTimersByTime(1000)
    countdown.start(second)
    vi.advanceTimersByTime(COUNTDOWN_MS)
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('Escape cancels while bound and is inert after release', () => {
    const onComplete = vi.fn()
    const countdown = new CopilotCountdown(COUNTDOWN_MS)
    countdown.start(onComplete)
    const release = bindEscapeCancel(() => countdown.cancel())
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    release()
    countdown.start(onComplete)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    vi.advanceTimersByTime(COUNTDOWN_MS)
    expect(onComplete).toHaveBeenCalledTimes(1)
  })
})
