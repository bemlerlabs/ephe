/**
 * Ephe — store: compactSession + renameSession (phase F1/F3)
 *
 * GIVEN  an active session with >28 messages
 * WHEN   compactSession()
 * THEN   messages = system ledger + the last 12 + 1 indicator message
 * AND    persist (debounced) + stats.changed=true
 *
 * GIVEN  an active session
 * WHEN   renameSession(id, a new title)
 * THEN   the title is updated and currentSession stays consistent
 */
import { describe, it, expect, beforeEach } from 'vitest'
import i18n from '@/i18n'
import { useChatStore } from './chatStore'
import type { ChatMessage } from '@/types'

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

function seedMessages(n: number) {
  const st = useChatStore.getState()
  const msgs: ChatMessage[] = Array.from({ length: n }, (_, i) => ({
    id: `m${i}`,
    role: i % 2 === 0 ? 'user' : 'assistant',
    content: `Nachricht ${i} ${'x'.repeat(40)}`,
    timestamp: Date.now() + i,
  }))
  const sid = st.activeSessionId!
  useChatStore.setState((s) => ({
    sessions: s.sessions.map((x) => (x.id === sid ? { ...x, messages: msgs } : x)),
    currentSession: s.currentSession ? { ...s.currentSession, messages: msgs } : null,
  }))
}

describe('chatStore compactSession/renameSession (Phase F)', () => {
  beforeEach(async () => {
    // The indicator strings are localised — the test environment is jsdom (en default).
    // Set de explicitly so the assertions stay language-stable.
    await i18n.changeLanguage('de')
    resetStore()
    useChatStore.getState().createSession('Test-Sitzung')
  })

  it('GIVEN 30 Messages WHEN compactSession THEN first+Ledger + 10 + Indikator (13 total)', () => {
    seedMessages(30)
    const { changed, stats } = useChatStore.getState().compactSession()

    expect(changed).toBe(true)
    expect(stats!.changed).toBe(true)
    // W18: older = messages[1:-10] = 19
    expect(stats!.compactedCount).toBe(19)

    const cs = useChatStore.getState().currentSession!
    // first(1) + ledger(1) + recent(10) + indicator(1) = 13
    expect(cs.messages).toHaveLength(13)
    expect(cs.messages[0]!.role).toBe('user') // the protected first message
    expect(cs.messages[1]!.role).toBe('system') // Ledger
    expect(cs.messages[1]!.content).toContain('Working Memory Ledger')
    expect(cs.messages[12]!.role).toBe('system') // the compact indicator message
    expect(cs.messages[12]!.content).toContain('Kompakt')

    // Wave 2/B4: one action, one compaction — a second ledger or a second indicator
    // would mean the trigger fired twice for the same click.
    const contents = cs.messages.map((m) => String(m.content ?? ''))
    expect(contents.filter((c) => c.includes('Working Memory Ledger'))).toHaveLength(1)
    expect(contents.filter((c) => c.includes('Kompakt'))).toHaveLength(1)
  })

  it('GIVEN 10 Messages WHEN compactSession THEN unchanged (changed=false)', () => {
    seedMessages(10)
    const { changed } = useChatStore.getState().compactSession()
    expect(changed).toBe(false)
    expect(useChatStore.getState().currentSession!.messages).toHaveLength(10)
  })

  it('GIVEN Session WHEN renameSession THEN title geupdatet (getrimmt)', () => {
    const st = useChatStore.getState()
    const sid = st.activeSessionId!
    st.renameSession(sid, '  Meines  ')
    expect(useChatStore.getState().currentSession!.title).toBe('Meines')
    expect(useChatStore.getState().sessions[0]!.title).toBe('Meines')
  })

  it('GIVEN leerer Titel WHEN renameSession THEN keine Änderung', () => {
    const st = useChatStore.getState()
    const sid = st.activeSessionId!
    st.renameSession(sid, '   ')
    expect(useChatStore.getState().currentSession!.title).toBe('Test-Sitzung')
  })
})
