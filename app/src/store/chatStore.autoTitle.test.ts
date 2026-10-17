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

describe('Session-Auto-Titel (G2)', () => {
  beforeEach(resetStore)

  it('erste User-Message setzt den Titel (Default-Titel ersetzt)', () => {
    useChatStore.getState().createSession()
    useChatStore.getState().addMessage('user', 'Wie baue ich eine REST-API in FastAPI?')

    expect(useChatStore.getState().currentSession!.title).toBe(
      'Wie baue ich eine REST-API in FastAPI?',
    )
  })

  it('Titel wird an ~48 Zeichen an Wortgrenze gekappt', () => {
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

  it('nur die ERSTE User-Message titelt — spätere ändern nichts', () => {
    useChatStore.getState().createSession()
    useChatStore.getState().addMessage('user', 'Erste Frage')
    useChatStore.getState().addMessage('user', 'Zweite Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('Erste Frage')
  })

  it('Assistant-Messages titeln nicht', () => {
    useChatStore.getState().createSession()
    useChatStore.getState().addMessage('assistant', 'Antwort ohne Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('New task')
  })

  it('manuelles Rename schützt vor Auto-Titel (titleCustom)', () => {
    useChatStore.getState().createSession()
    const id = useChatStore.getState().activeSessionId!
    useChatStore.getState().renameSession(id, 'Mein Projekt')
    useChatStore.getState().addMessage('user', 'Erste Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('Mein Projekt')
  })

  it('Session mit explizitem Titel (createSession-Titel) wird nicht auto-geändert', () => {
    useChatStore.getState().createSession('Importierte Sitzung')
    useChatStore.getState().addMessage('user', 'Erste Frage')
    expect(useChatStore.getState().currentSession!.title).toBe('Importierte Sitzung')
  })

  it('titleCustom wird bei renameSession gesetzt und überlebt addMessage', () => {
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
