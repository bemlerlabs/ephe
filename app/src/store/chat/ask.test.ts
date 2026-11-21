/**
 * G1 — the store side of the live ask.
 *
 * The stream's `ask_user` frame opens the question on the assistant message of the
 * RUNNING turn (`ask.status === 'waiting'`), and the terminal states close it:
 * answered / timeout / expired. The bubble reads exactly these fields, so the
 * transitions are pinned here rather than inferred from the frame names.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '@/store/chatStore'

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

function activeAsk() {
  const msgs = useChatStore.getState().currentSession!.messages
  return msgs[msgs.length - 1]!.ask
}

describe('chatStore ask actions (G1)', () => {
  beforeEach(() => {
    resetStore()
    useChatStore.getState().createSession('Ask')
    useChatStore.getState().startTurn()
  })

  it('resolveAsk opens the question on the running turn with the server values', () => {
    useChatStore.getState().resolveAsk({
      token: 'ask-1',
      question: 'Welcher Branch?',
      options: ['main', 'wt/n1-ask'],
      recommendation: 'main',
      timeoutS: 180,
      defaultAnswer: 'main',
    })

    expect(activeAsk()).toMatchObject({
      token: 'ask-1',
      question: 'Welcher Branch?',
      options: [{ label: 'main' }, { label: 'wt/n1-ask' }],
      recommendation: 'main',
      timeoutS: 180,
      defaultAnswer: 'main',
      status: 'waiting',
    })
  })

  it('markAskAnswered closes the ask with the text that went into the run', () => {
    const s = useChatStore.getState()
    s.resolveAsk({ token: 'ask-1', question: 'Q?', options: ['a', 'b'] })
    useChatStore.getState().markAskAnswered('ask-1', 'b')

    expect(activeAsk()).toMatchObject({ status: 'answered', answer: 'b' })
  })

  it('markAskAnswered with another token leaves the open question alone', () => {
    const s = useChatStore.getState()
    s.resolveAsk({ token: 'ask-1', question: 'Q?', options: ['a', 'b'] })
    useChatStore.getState().markAskAnswered('ask-old', 'b')

    expect(activeAsk()!.status).toBe('waiting')
    expect(activeAsk()!.answer).toBeUndefined()
  })

  it('markAskTimedOut keeps the default the run continued on', () => {
    const s = useChatStore.getState()
    s.resolveAsk({ token: 'ask-1', question: 'Q?', options: ['a'], defaultAnswer: 'a' })
    useChatStore.getState().markAskTimedOut('ask-1')

    expect(activeAsk()).toMatchObject({ status: 'timeout', defaultAnswer: 'a' })
  })

  it('markAskExpired marks an answer that could not reach the run', () => {
    const s = useChatStore.getState()
    s.resolveAsk({ token: 'ask-1', question: 'Q?', options: ['a'] })
    useChatStore.getState().markAskExpired('ask-1')

    expect(activeAsk()!.status).toBe('expired')
  })
})
