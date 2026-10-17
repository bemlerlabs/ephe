/**
 * Z37 (parity, 2026-09-09): the session fork as a store primitive.
 *
 * `branchSession(fromMsgId)` copies the prefix of the active session (including
 * the target message) into a new session with a `parentId`, activates the branch
 * and persists both entries. Four cases: new id, prefix length, parent_id, and
 * the cursor at the end (active).
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

describe('chatStore.branchSession (Z37)', () => {
  beforeEach(() => {
    resetStore()
    useChatStore.getState().createSession('Basis')
    const s = useChatStore.getState()
    s.addMessage('user', 'eins')
    s.addMessage('assistant', 'zwei')
    s.addMessage('user', 'drei')
  })

  it('neue Session erhaelt eigene id + Praefix bis zur Ziel-Message', () => {
    const st = useChatStore.getState()
    const msgs = st.currentSession!.messages
    const targetId = msgs[1]!.id // 'zwei' → prefix = 2 messages // language-gate: ignore (names the asserted sample-message fixture content)
    st.branchSession(targetId)
    const after = useChatStore.getState()
    const branched = after.sessions.find((x) => x.id !== st.activeSessionId && x.parentId)
    expect(branched).toBeTruthy()
    expect(branched!.messages.length).toBe(2)
    expect(branched!.messages[0]!.content).toBe('eins')
    expect(branched!.messages[1]!.content).toBe('zwei')
  })

  it('parent_id zeigt auf die Ursprungssession', () => {
    const st = useChatStore.getState()
    const targetId = st.currentSession!.messages[0]!.id
    st.branchSession(targetId)
    const after = useChatStore.getState()
    const branched = after.sessions.find((x) => x.parentId === st.activeSessionId)
    expect(branched).toBeTruthy()
  })

  it('Zweig ist nach dem Fork die aktive Session (Cursor am Ende)', () => {
    const st = useChatStore.getState()
    const oldActive = st.activeSessionId
    const targetId = st.currentSession!.messages[2]!.id
    st.branchSession(targetId)
    const after = useChatStore.getState()
    expect(after.activeSessionId).not.toBe(oldActive)
    expect(after.currentSession!.id).toBe(after.activeSessionId)
    expect(after.currentSession!.messages.length).toBe(3)
  })

  it('unbekannte message id laesst den Store unveraendert', () => {
    const st = useChatStore.getState()
    const before = useChatStore.getState().sessions.length
    st.branchSession('no-such-id')
    expect(useChatStore.getState().sessions.length).toBe(before)
  })
})
