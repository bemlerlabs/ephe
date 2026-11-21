/**
 * The gate's own state and its own clock, read with `now` injected.
 *
 * GIVEN  gate records in every state of the state machine
 * WHEN   the card-facing predicates read them
 * THEN   a closed gate is closed and an open one inside its window is answerable
 * AND    an expiry is an expiry: it carries no outcome and the row word names no hand
 */
import { describe, it, expect } from 'vitest'
import {
  SANDBOX_APPROVAL_WINDOW_MS,
  gateIsAnswerable,
  gateIsClosed,
  gateRowWord,
  gateToken,
  gatesPastWindow,
} from './sandboxGate'
import type { ApprovalGate, ToolCall } from '@/types'

const T0 = 1_700_000_000_000
const word = (key: string) => key

function gated(over: Partial<ToolCall> = {}, gate: Partial<ApprovalGate> = {}): ToolCall {
  return {
    id: 'c1',
    name: 'run_shell',
    args: { command: 'ls' },
    status: 'waiting',
    description: 'tok-1',
    ...over,
    approval: { token: 'tok-1', openedAt: T0, state: 'waiting', ...gate },
  }
}

describe('sandboxGate', () => {
  it('reads the token off the gate, and off description in an old transcript', () => {
    expect(gateToken(gated())).toBe('tok-1')
    const legacy: ToolCall = {
      id: 'c2',
      name: 'run_shell',
      args: {},
      status: 'waiting',
      description: 'tok-legacy',
    }
    expect(gateToken(legacy)).toBe('tok-legacy')
  })

  it('counts only an answered or expired gate as closed', () => {
    expect(gateIsClosed(gated())).toBe(false)
    expect(gateIsClosed(gated({}, { state: 'submitting' }))).toBe(false)
    expect(
      gateIsClosed(gated({}, { state: 'answered', outcome: 'allowed', closedBy: 'you' })),
    ).toBe(true)
    expect(gateIsClosed(gated({}, { state: 'expired', closedBy: 'server' }))).toBe(true)
    // A row whose status already says the window is over is closed whatever the
    // gate record still claims — the row is what the transcript persisted.
    expect(gateIsClosed(gated({ status: 'expired' }))).toBe(true)
  })

  it('is answerable only while waiting inside the window', () => {
    expect(gateIsAnswerable(gated(), T0 + 1000)).toBe(true)
    expect(gateIsAnswerable(gated(), T0 + SANDBOX_APPROVAL_WINDOW_MS - 1)).toBe(true)
    expect(gateIsAnswerable(gated(), T0 + SANDBOX_APPROVAL_WINDOW_MS)).toBe(false)
    expect(gateIsAnswerable(gated({}, { state: 'submitting' }), T0)).toBe(false)
    expect(gateIsAnswerable(gated({}, { state: 'answered' }), T0)).toBe(false)
    expect(gateIsAnswerable(gated({}, { state: 'expired' }), T0)).toBe(false)
  })

  it('is answerable for a pre-gate transcript row that is still waiting', () => {
    const legacy: ToolCall = {
      id: 'c3',
      name: 'run_shell',
      args: {},
      status: 'waiting',
      description: 'tok-legacy',
    }
    expect(gateIsAnswerable(legacy, T0)).toBe(true)
    expect(gateIsAnswerable({ ...legacy, status: 'approved' }, T0)).toBe(false)
  })

  it('names the gates whose window ran out and leaves the closed ones alone', () => {
    const calls = [
      gated({ id: 'a' }, { state: 'answered', outcome: 'denied', closedBy: 'you' }),
      gated({ id: 'b', description: 'tok-b' }, { token: 'tok-b', openedAt: T0 }),
      gated({ id: 'c', description: 'tok-c' }, { token: 'tok-c', openedAt: T0 + 1000 }),
      gated(
        { id: 'd', description: 'tok-d' },
        { token: 'tok-d', openedAt: T0, state: 'submitting' },
      ),
    ]
    expect(gatesPastWindow(calls, T0 + SANDBOX_APPROVAL_WINDOW_MS)).toEqual(['tok-b'])
    expect(gatesPastWindow(calls, T0)).toEqual([])
  })

  it('gives each gate state the row word that matches what actually happened', () => {
    // Inside the window it is a wait; past the window the row says so even before
    // the tick has written the expiry.
    expect(gateRowWord(gated(), word, T0 + 1_000)).toBe('chat.toolWaiting')
    expect(gateRowWord(gated(), word, T0 + SANDBOX_APPROVAL_WINDOW_MS)).toBe(
      'chat.toolApproval.rowExpired',
    )
    expect(gateRowWord(gated({}, { state: 'submitting' }), word)).toBe('chat.toolApproval.sending')
    expect(gateRowWord(gated({}, { state: 'expired' }), word)).toBe('chat.toolApproval.rowExpired')
    expect(gateRowWord(gated({}, { state: 'answered', closedBy: 'server' }), word)).toBe(
      'chat.toolApproval.rowSpent',
    )
    // Answered by a hand: the row falls through to the plain status word, which is
    // the outcome of the call itself and not a word the gate invents.
    expect(
      gateRowWord(gated({ status: 'approved' }, { state: 'answered', closedBy: 'you' }), word),
    ).toBe(null)
    const legacy: ToolCall = { id: 'c4', name: 'run_shell', args: {}, status: 'completed' }
    expect(gateRowWord(legacy, word)).toBeNull()
  })
})
