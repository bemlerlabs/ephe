/**
 * S23: a tool call without a call_id still keeps its result and its reason.
 *
 * The frames from an engine that names no call carry no id; the store matched
 * them by name and copied status and arguments but dropped the result and the
 * reason code, so the card said Failed and never said why.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { useChatStore } from './chatStore'

function activeCalls() {
  const cs = useChatStore.getState().currentSession!
  for (let i = cs.messages.length - 1; i >= 0; i--) {
    const m = cs.messages[i]!
    if (m.role === 'assistant') return m.tool_calls ?? []
  }
  return []
}

function resetStore() {
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    checkpoints: {},
  })
}

describe('tool_done without a call_id', () => {
  beforeEach(() => {
    resetStore()
    useChatStore.getState().createSession('S23')
  })

  it('keeps the result and the reason on the open call', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.appendChunk('x')
    s.upsertToolCall({ name: 'fetch_url', args: { url: 'https://example.test/x' }, status: 'pending' })
    s.upsertToolCall({
      name: 'fetch_url',
      result: '[fetch failed] https://example.test/x answered HTTP 404.',
      status: 'failed',
      reasonCode: 'fetch_http_error',
      reasonParams: { status: '404', url: 'https://example.test/x' },
    })

    const call = activeCalls().find((c) => c.name === 'fetch_url')

    expect(call?.status).toBe('failed')
    expect(call?.result).toContain('fetch failed')
    expect(call?.reason_code).toBe('fetch_http_error')
    expect(call?.reason_params).toEqual({ status: '404', url: 'https://example.test/x' })
  })
})
