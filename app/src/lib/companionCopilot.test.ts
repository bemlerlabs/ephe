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
import { canRememberShape } from './companionRemember'

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

/** The shell tool is the one that carries a command; the co-pilot knows no other. */
function waitingTool(command: string) {
  return { name: 'run_shell', args: { command }, description: 'token-1' }
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
    'pytest /tmp/a',
    'pytest ~/a',
    'git diff ~/a',
    'echo ${HOME}',
    'git diff --output=x',
    'git -c a=b status',
    'pytest -o a=b',
    'pytest --override-ini=a=b',
    'pytest --rootdir /tmp/a',
    'cargo test --config a=b',
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

  it('only the shell tool can earn an automatic approval', () => {
    const other = { name: 'execute_code', args: { command: 'pytest' }, description: 't' }
    const finding = findCopilotTarget(snap({ waitingTool: other }), 'copilot')
    expect(finding).toMatchObject({ verdict: 'warn_only', actionKey: 'copilot.action.noApprove' })
  })

  it('scout reads a non-shell tool as a risk it would not approve', () => {
    const other = { name: 'write_file', args: { command: 'pytest' }, description: 't' }
    const finding = findCopilotTarget(snap({ waitingTool: other }), 'scout')
    expect(finding).toMatchObject({ verdict: 'focus', actionKey: 'copilot.action.reviewRisk' })
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

describe('read-only workspace inspection (QD-008)', () => {
  it.each([
    'ls -1 .',
    'ls -la',
    'cat README.md',
    'head -n 20 notes.md',
    'tail -5 log.txt',
    'wc -l notes.md',
    'stat package.json',
    'du -sh .',
    'pwd',
    'which git',
    'file a.png',
    'rg todo',
    'grep -i error log.txt',
    'find . -maxdepth 2',
    'find . -type f -name "*.md"',
  ])('reads %j as safe inspection', (command) => {
    expect(classifyShellCommand(command)).toBe('auto_act')
  })

  it.each([
    'find . -delete',
    'find . -exec rm {} ;',
    'find . -execdir sh -c id ;',
    'find . -fprint out.txt',
    'sed -i "" s/a/b/ notes.md',
    'sed -ni 1p notes.md',
    'sed --in-place s/a/b/ notes.md',
    'ls /etc',
    'cat ~/.ssh/id_rsa',
    'cat ../outside.txt',
    'grep error . > hits.txt',
    'ls | wc -l',
  ])('still refuses %j', (command) => {
    expect(classifyShellCommand(command)).toBe('warn_only')
  })
})

describe('user-taught shapes (QD-008)', () => {
  it('offers to remember a plain verb and never a forbidden line', () => {
    expect(canRememberShape('jq . package.json')).toBe(true)
    expect(canRememberShape('rm -rf .')).toBe(false)
    expect(canRememberShape('jq . a.json && rm b')).toBe(false)
    expect(canRememberShape('./run.sh')).toBe(false)
  })

  it('approves a remembered verb, and the fence still runs per command', () => {
    expect(classifyShellCommand('jq . package.json')).toBe('warn_only')
    expect(classifyShellCommand('jq . package.json', ['jq'])).toBe('auto_act')
    expect(classifyShellCommand('jq . a.json && rm b', ['jq'])).toBe('warn_only')
    expect(classifyShellCommand('jq . a.json > out.json', ['jq'])).toBe('warn_only')
  })
})
