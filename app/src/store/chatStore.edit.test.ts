/**
 * G1.1 — messaging parity: edit / regenerate / retry
 *
 * GIVEN  chatStore with truncateAfter / updateMessageContent / removeMessage
 * WHEN   a user message is edited or an assistant message regenerated
 * THEN   truncateAfter cuts everything AFTER the target message (the target stays)
 * AND    updateMessageContent replaces the content of a message by id
 * AND    removeMessage deletes a single message by id (the retry of the error case)
 * AND    none of this touches other sessions
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

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

/** Build a session with [user a, assistant b, user c, assistant d] */
function seedConversation() {
  useChatStore.getState().createSession('Test')
  const s = useChatStore.getState()
  s.addMessage('user', 'a')
  s.addMessage('assistant', 'b')
  s.addMessage('user', 'c')
  s.addMessage('assistant', 'd')
  return useChatStore.getState().currentSession!.messages
}

describe('chatStore Edit/Regenerate/Retry-Actions (G1)', () => {
  beforeEach(resetStore)

  it('truncateAfter removes everything after the target message (the target stays)', () => {
    const msgs = seedConversation()
    useChatStore.getState().truncateAfter(msgs[1]!.id)

    const after = useChatStore.getState().currentSession!.messages
    expect(after.map((m) => m.content)).toEqual(['a', 'b'])
  })

  it('truncateAfter on the last message is a no-op (nothing torn away)', () => {
    const msgs = seedConversation()
    useChatStore.getState().truncateAfter(msgs[3]!.id)
    expect(useChatStore.getState().currentSession!.messages).toHaveLength(4)
  })

  it('truncateAfter with an unknown id changes nothing', () => {
    seedConversation()
    useChatStore.getState().truncateAfter('gibt-es-nicht')
    expect(useChatStore.getState().currentSession!.messages).toHaveLength(4)
  })

  it('truncateAfter without an active session is a no-op', () => {
    seedConversation()
    useChatStore.setState({ activeSessionId: null, currentSession: null })
    useChatStore.getState().truncateAfter('egal')
    expect(useChatStore.getState().sessions).toHaveLength(1)
  })

  it('truncateAfter touches only the active session', () => {
    seedConversation()
    useChatStore.getState().createSession('Andere')
    const otherId = useChatStore.getState().activeSessionId!
    useChatStore.setState({ activeSessionId: null, currentSession: null })
    // fill the other session
    useChatStore.setState((s) => ({
      activeSessionId: otherId,
      currentSession: s.sessions.find((x) => x.id === otherId) ?? null,
    }))
    useChatStore.getState().addMessage('user', 'x')
    const otherMsgs = useChatStore.getState().currentSession!.messages
    useChatStore.getState().truncateAfter(otherMsgs[0]!.id)

    // the active (second) session got truncated …
    expect(useChatStore.getState().currentSession!.messages).toHaveLength(1)
    // … the first session untouched
    const first = useChatStore.getState().sessions.find((s) => s.title === 'Test')!
    expect(first.messages).toHaveLength(4)
  })

  it('updateMessageContent replaces the content by id', () => {
    const msgs = seedConversation()
    useChatStore.getState().updateMessageContent(msgs[0]!.id, 'a — bearbeitet')

    const after = useChatStore.getState().currentSession!.messages
    expect(after[0]!.content).toBe('a — bearbeitet')
    expect(after).toHaveLength(4)
  })

  it('removeMessage deletes exactly the target message (the retry failure case)', () => {
    const msgs = seedConversation()
    useChatStore.getState().removeMessage(msgs[3]!.id)

    const after = useChatStore.getState().currentSession!.messages
    expect(after.map((m) => m.content)).toEqual(['a', 'b', 'c'])
  })

  it('the edit flow updates content plus truncateAfter, ending the session at the edit', () => {
    const msgs = seedConversation()
    const store = useChatStore.getState()
    store.updateMessageContent(msgs[2]!.id, 'c — neu')
    store.truncateAfter(msgs[2]!.id)

    const after = useChatStore.getState().currentSession!.messages
    expect(after.map((m) => m.content)).toEqual(['a', 'b', 'c — neu'])
    expect(after[after.length - 1]!.role).toBe('user')
  })
})
