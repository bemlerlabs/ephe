/**
 * G2 — session auto-title (AI-client parity)
 *
 * GIVEN  a session carrying the default title ("New Session")
 * WHEN   the first user message arrives
 * THEN   the title is derived from that message (~48 characters, word boundary)
 * AND    manual renames (titleCustom) are NEVER overwritten
 * AND    sessions with an explicit title are left alone
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

describe('the session auto title (G2)', () => {
  beforeEach(resetStore)

  it('the first user message sets the title (the default is replaced)', () => {
    useChatStore.getState().createSession()
    useChatStore.getState().addMessage('user', 'Wie baue ich eine REST-API in FastAPI?')

    expect(useChatStore.getState().currentSession!.title).toBe(
      'Wie baue ich eine REST-API in FastAPI?',
    )
  })

  it('the title is cut near 48 characters at a word boundary', () => {
    useChatStore.getState().createSession()
    useChatStore
      .getState()
      .addMessage(
        'user',
        'Ein sehr langer Satz der weit über die Kapplungsgrenze hinausgeht und trotzdem sauber enden muss',
      )
    const title = useChatStore.getState().currentSession!.title
    expect(title.length).toBeLessThanOrEqual(50)
    expect(title.endsWith('…')).toBe(true)
    // no chopped-off word
    expect(title.endsWith(' ')).toBe(false)
  })

  it('only the first user message titles, later ones change nothing', () => {
    useChatStore.getState().createSession()
    useChatStore.getState().addMessage('user', 'Erste Frage')
    useChatStore.getState().addMessage('user', 'Zweite Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('Erste Frage')
  })

  it('assistant messages do not title', () => {
    useChatStore.getState().createSession()
    useChatStore.getState().addMessage('assistant', 'Antwort ohne Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('New task')
  })

  it('a manual rename is protected from the auto title (titleCustom)', () => {
    useChatStore.getState().createSession()
    const id = useChatStore.getState().activeSessionId!
    useChatStore.getState().renameSession(id, 'Mein Projekt')
    useChatStore.getState().addMessage('user', 'Erste Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('Mein Projekt')
  })

  it('a session with an explicit title from createSession is not auto-changed', () => {
    useChatStore.getState().createSession('Importierte Sitzung')
    useChatStore.getState().addMessage('user', 'Erste Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('Importierte Sitzung')
  })

  it('renameSession sets titleCustom and it survives addMessage', () => {
    useChatStore.getState().createSession()
    const id = useChatStore.getState().activeSessionId!
    useChatStore.getState().addMessage('user', 'Erste Frage')
    useChatStore.getState().renameSession(id, 'Neuer Name')
    useChatStore.getState().addMessage('user', 'Zweite Frage')
    const s = useChatStore.getState().sessions.find((x) => x.id === id)!
    expect(s.titleCustom).toBe(true)
    expect(s.title).toBe('Neuer Name')
  })
})
