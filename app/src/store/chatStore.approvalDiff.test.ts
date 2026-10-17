/**
 * Wave B1: resolveSandbox attaches the real diff preview to the waiting call.
 *
 * GIVEN  a running assistant turn
 * WHEN   resolveSandbox(token, tool, args, rememberable, diff)
 * THEN   the last waiting call carries description === token AND approval_diff === diff
 * AND    without a diff field approval_diff stays undefined (the run_shell path).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

function waitingCall() {
  const cs = useChatStore.getState().currentSession!
  const msgs = cs.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    const call = msgs[i]!.tool_calls?.find((c) => c.status === 'waiting')
    if (call) return call
  }
  throw new Error('kein waiting-Tool-Call')
}

describe('chatStore.resolveSandbox approval_diff (Wave B1)', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('Approval-Sitzung')
    useChatStore.getState().addMessage('user', 'aendere die datei')
    useChatStore.getState().startTurn()
  })

  it('verankert Token + echten Diff am waiting-Call', () => {
    useChatStore
      .getState()
      .resolveSandbox(
        'tok-123',
        'edit_file',
        { path: 'a.txt' },
        false,
        '--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-x\n+y',
      )
    const call = waitingCall()
    expect(call.description).toBe('tok-123')
    expect(call.approval_diff).toContain('+y')
  })

  it('laesst approval_diff undefined, wenn kein Diff mitkommt', () => {
    useChatStore.getState().resolveSandbox('tok-999', 'run_shell', { command: 'ls' }, false)
    const call = waitingCall()
    expect(call.description).toBe('tok-999')
    expect(call.approval_diff).toBeUndefined()
  })
})
