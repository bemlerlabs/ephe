import { describe, expect, it } from 'vitest'

import {
  countdownMs,
  findCopilotTarget,
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

describe('the countdown setting (QD-013)', () => {
  it('turns seconds into milliseconds and clamps to 0-10 s', () => {
    expect(countdownMs(2.5)).toBe(2500)
    expect(countdownMs(0)).toBe(0)
    expect(countdownMs(10)).toBe(10000)
    expect(countdownMs(12)).toBe(10000)
    expect(countdownMs(-3)).toBe(0)
  })

  it('falls back to the shipped 2.5 s when nothing is configured', () => {
    expect(countdownMs(undefined)).toBe(2500)
    expect(countdownMs(Number.NaN)).toBe(2500)
  })

  it('offers the codebase index only when nothing more urgent waits', () => {
    const idle = snap({ codebaseIdle: true })
    expect(findCopilotTarget(idle, 'copilot')).toMatchObject({
      target: 'codebase_index',
      verdict: 'auto_act',
      actionKey: 'copilot.action.indexCodebase',
    })
    expect(findCopilotTarget(idle, 'scout')).toMatchObject({
      target: 'codebase_index',
      verdict: 'focus',
    })
    expect(findCopilotTarget(idle, 'perch')).toBeNull()

    const busy = snap({ codebaseIdle: true, waitingTool: { name: 'run_shell', args: { command: 'pytest -q' } } })
    expect(findCopilotTarget(busy, 'copilot')?.target).toBe('tool_approval')
  })
})
