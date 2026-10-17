/**
 * Round 3 — "Analyzing request…" kept spinning forever inside finished bubbles
 *
 * GIVEN  an assistant message with activities in status 'running'
 * WHEN   finishTurn() ends the turn
 * THEN   ALL still-running activities are closed to 'done'
 * AND    already completed/failed activities stay untouched
 * AND    streaming is false and streamMeta is reset completely
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

describe('finishTurn schließt offene Activities (Analyzing-request-Fix)', () => {
  beforeEach(resetStore)

  it('running-Activity wird beim Turn-Ende auf done gesetzt', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    store.upsertActivity({ label: 'Analyzing request…', status: 'running' })

    useChatStore.getState().finishTurn()

    const msg = useChatStore
      .getState()
      .currentSession!.messages.find((m) => m.role === 'assistant')!
    expect(msg.streaming).toBe(false)
    expect(msg.activities?.find((a) => a.label === 'Analyzing request…')?.status).toBe('done')
  })

  it('gemischte Status: nur running wird geschlossen, done/failed bleiben', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    store.upsertActivity({ label: 'Phase A', status: 'running' })
    store.upsertActivity({ label: 'Phase B', status: 'running' })
    store.upsertActivity({ label: 'Phase B', status: 'done' })
    store.upsertActivity({ label: 'Phase C', status: 'failed' })

    useChatStore.getState().finishTurn()

    const msg = useChatStore
      .getState()
      .currentSession!.messages.find((m) => m.role === 'assistant')!
    const byLabel = Object.fromEntries((msg.activities ?? []).map((a) => [a.label, a.status]))
    expect(byLabel['Phase A']).toBe('done')
    expect(byLabel['Phase B']).toBe('done')
    expect(byLabel['Phase C']).toBe('failed')
  })

  it('P4-D/N-Regression: „SubAgent 1 (role)" und „SubAgent 1" matched denselben Eintrag', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    // started creates the entry with a role suffix …
    store.upsertActivity({
      label: 'SubAgent 1 (general-purpose)',
      status: 'running',
      detail: 'task: x',
    })
    // … tool/done upsert without the suffix — without label normalisation the entry would stay "running"
    store.upsertActivity({ label: 'SubAgent 1', status: 'running', detail: 'read_file: …' })
    store.upsertActivity({ label: 'SubAgent 1', status: 'done', detail: 'Fertig.' })

    const msg = useChatStore
      .getState()
      .currentSession!.messages.find((m) => m.role === 'assistant')!
    const acts = msg.activities ?? []
    expect(acts.length).toBe(1)
    expect(acts[0]!.label).toBe('SubAgent 1 (general-purpose)')
    expect(acts[0]!.status).toBe('done')
    expect(acts[0]!.detail).toBe('Fertig.')
  })
})
