/**
 * Ephe — PWA-Chat-UX-Plan, Task C1: applyStreamEvent Reducer
 *
 * GIVEN  applyStreamEvent (event → store-action mapping) + mock store
 * WHEN   all 25 stream events are run through
 * THEN   exactly the right store actions fire (order + payload)
 * AND    model_info / swarm_done / vision_* = defined no-ops
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { applyStreamEvent } from './streamActions'

function mockStore() {
  return {
    startTurn: vi.fn(),
    appendChunk: vi.fn(),
    appendThinking: vi.fn(),
    replaceText: vi.fn(),
    upsertToolCall: vi.fn(),
    upsertActivity: vi.fn(),
    setTurnId: vi.fn(),
    attachArtifact: vi.fn(),
    setPlan: vi.fn(),
    beginGoal: vi.fn(),
    advanceGoal: vi.fn(),
    resolveSandbox: vi.fn(),
    resolveAsk: vi.fn(),
    markAskTimedOut: vi.fn(),
    markStreamError: vi.fn(),
    markLastUsage: vi.fn(),
    markBudgetReached: vi.fn(),
    setReflecting: vi.fn(),
    setRevising: vi.fn(),
    setQualityCheck: vi.fn(),
    finishTurn: vi.fn(),
    beginHelperChat: vi.fn(),
    stepHelperChat: vi.fn(),
    setProgress: vi.fn(),
    endHelperChat: vi.fn(),
  }
}

describe('applyStreamEvent (Event → Store-Action Mapping)', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('thinking_start → startTurn (Turn-Start vor dem ersten chunk)', () => {
    applyStreamEvent({ type: 'thinking_start' }, store)
    expect(store.startTurn).toHaveBeenCalledTimes(1)
  })

  it('thinking_chunk → appendThinking mit exakter Data (KI-Client-Parität)', () => {
    applyStreamEvent({ type: 'thinking_chunk', data: 'Ich überlege…' }, store)
    expect(store.appendThinking).toHaveBeenCalledTimes(1)
    expect(store.appendThinking).toHaveBeenCalledWith('Ich überlege…')
    // Thinking chunks must NOT enter the content-chunk flow (appendChunk)
    expect(store.appendChunk).not.toHaveBeenCalled()
  })

  it('chunk → appendChunk mit exakter Data', () => {
    applyStreamEvent({ type: 'chunk', data: 'Hallo ' }, store)
    applyStreamEvent({ type: 'chunk', data: 'Welt' }, store)
    expect(store.appendChunk).toHaveBeenNthCalledWith(1, 'Hallo ')
    expect(store.appendChunk).toHaveBeenNthCalledWith(2, 'Welt')
  })

  it('replace_text → replaceText (Revision ersetzt Content komplett)', () => {
    applyStreamEvent({ type: 'replace_text', text: 'sauber' }, store)
    expect(store.replaceText).toHaveBeenCalledWith('sauber')
  })

  it('activity → upsertActivity (cmd als Label, Status-Mapping)', () => {
    applyStreamEvent({ type: 'activity', cmd: 'search_web()', status: 'running' }, store)
    expect(store.upsertActivity).toHaveBeenCalledWith({
      label: 'search_web()',
      status: 'running',
    })
    applyStreamEvent({ type: 'activity', cmd: 'search_web() → done', status: 'done' }, store)
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'search_web() → done',
      status: 'done',
    })
  })

  it('tool_start → upsertToolCall (pending); tool_done → upsertToolCall (completed + result)', () => {
    applyStreamEvent({ type: 'tool_start', tool: 'run_shell', args: { command: 'ls' } }, store)
    expect(store.upsertToolCall).toHaveBeenCalledWith({
      name: 'run_shell',
      args: { command: 'ls' },
      status: 'pending',
    })
    applyStreamEvent({ type: 'tool_done', tool: 'run_shell', result: 'ok' }, store)
    expect(store.upsertToolCall).toHaveBeenLastCalledWith({
      name: 'run_shell',
      result: 'ok',
      status: 'completed',
    })
  })

  it('phase → upsertActivity (name als Label)', () => {
    applyStreamEvent({ type: 'phase', name: 'Recherche', status: 'running' }, store)
    expect(store.upsertActivity).toHaveBeenCalledWith({
      label: 'Recherche',
      status: 'running',
    })
  })

  it('quality_check → setQualityCheck (nur bei status=running auf true)', () => {
    applyStreamEvent({ type: 'quality_check', status: 'running', skill: 's' }, store)
    expect(store.setQualityCheck).toHaveBeenCalledWith(true)
    applyStreamEvent({ type: 'quality_check', status: 'done', skill: 's' }, store)
    expect(store.setQualityCheck).toHaveBeenLastCalledWith(false)
  })

  it('reflect → setReflecting; revision → setRevising(true)', () => {
    applyStreamEvent({ type: 'reflect', status: 'running' }, store)
    expect(store.setReflecting).toHaveBeenCalledWith(true)
    applyStreamEvent({ type: 'reflect', status: 'done', needs_revision: true }, store)
    expect(store.setReflecting).toHaveBeenLastCalledWith(false)
    applyStreamEvent({ type: 'revision', reason: 'unvollständig' }, store)
    expect(store.setRevising).toHaveBeenCalledWith(true)
  })

  it('sandbox_confirm → resolveSandbox (Token + Tool + Args + optionaler Diff)', () => {
    applyStreamEvent(
      {
        type: 'sandbox_confirm',
        token: 'abc-123',
        tool: 'run_shell',
        args: { command: 'rm -rf x' },
      },
      store,
    )
    expect(store.resolveSandbox).toHaveBeenCalledWith(
      'abc-123',
      'run_shell',
      { command: 'rm -rf x' },
      undefined,
      undefined,
    )
  })

  it('sandbox_confirm mit diff → Diff als 5. Argument an resolveSandbox', () => {
    applyStreamEvent(
      {
        type: 'sandbox_confirm',
        token: 'tok-d',
        tool: 'edit_file',
        args: { path: 'a.txt' },
        diff: '--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-x\n+y',
      },
      store,
    )
    expect(store.resolveSandbox).toHaveBeenCalledWith(
      'tok-d',
      'edit_file',
      { path: 'a.txt' },
      undefined,
      '--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-x\n+y',
    )
  })

  it('error → markStreamError (Nur die Message wird beendet — finishTurn erst bei done)', () => {
    applyStreamEvent({ type: 'error', msg: 'Ollama nicht erreichbar' }, store)
    expect(store.markStreamError).toHaveBeenCalledWith('Ollama nicht erreichbar', undefined)
  })

  it('done → finishTurn', () => {
    applyStreamEvent({ type: 'done' }, store)
    expect(store.finishTurn).toHaveBeenCalledTimes(1)
  })

  it('Swarm-Events → Activities (Agent-Feed)', () => {
    applyStreamEvent(
      { type: 'swarm_status', phase: 'planning', message: '🐝 Swarm V2 started' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: '🐝 Swarm V2 started',
      status: 'running',
    })
    applyStreamEvent(
      { type: 'swarm_created', swarm_id: 'sw-1', agents: [{ agent_id: 'a1', role: 'researcher', model: 'gemma4:e4b', task_spec_hash: 'h1' }, { agent_id: 'a2', role: 'researcher', model: 'gemma4:e4b', task_spec_hash: 'h2' }], model: 'gemma4:e4b' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Swarm: 2 Agents',
      status: 'done',
      detail: 'researcher · gemma4:e4b, researcher · gemma4:e4b',
    })
    applyStreamEvent(
      { type: 'swarm_agent_started', swarm_id: 'sw-1', agent_id: 'a1', subtask: 'X' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Agent a1',
      status: 'running',
      detail: 'X',
    })
    applyStreamEvent(
      { type: 'swarm_agent_done', swarm_id: 'sw-1', agent_id: 'a1', summary: 'Y' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Agent a1',
      status: 'done',
      detail: 'Y',
    })
  })

  it('R36-S: Subagent-Events → Activities (ein Feed-Eintrag pro agent_id)', () => {
    applyStreamEvent(
      {
        type: 'subagent_started',
        agent_id: 'subagent-1',
        role: 'researcher',
        task: 'Find numbers',
        model: 'm',
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'SubAgent subagent-1 (researcher)',
      status: 'running',
      detail: 'Find numbers',
    })
    applyStreamEvent(
      {
        type: 'subagent_tool',
        agent_id: 'subagent-1',
        tool: 'web_search',
        args_preview: '{"query":…}',
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'SubAgent subagent-1',
      status: 'running',
      detail: 'web_search: {"query":…}',
    })
    applyStreamEvent(
      { type: 'subagent_done', agent_id: 'subagent-1', status: 'ok', summary: 'Report ready' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'SubAgent subagent-1',
      status: 'done',
      detail: 'Report ready',
    })
    applyStreamEvent(
      {
        type: 'subagent_done',
        agent_id: 'subagent-2',
        status: 'timeout',
        summary: '[subagent timeout]',
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'SubAgent subagent-2',
      status: 'failed',
      detail: '[subagent timeout]',
    })
  })

  it('F-01: artifact → attachArtifact (Inhalt an Message) + Activity mit Dateinamen', () => {
    applyStreamEvent(
      {
        type: 'artifact',
        artifact: {
          id: 'art1',
          artifact_type: 'code_python',
          content: 'def fib():\n    ...',
          language: 'python',
          title: 'fib() — script.py',
          filename: 'script.py',
        },
      },
      store,
    )
    expect(store.attachArtifact).toHaveBeenCalledTimes(1)
    expect(store.attachArtifact).toHaveBeenCalledWith({
      id: 'art1',
      artifact_type: 'code_python',
      content: 'def fib():\n    ...',
      language: 'python',
      title: 'fib() — script.py',
      filename: 'script.py',
    })
    expect(store.upsertActivity).toHaveBeenCalledWith({
      label: 'Artifact: script.py',
      status: 'done',
    })
    // The content flow must not be touched by the artifact event
    expect(store.appendChunk).not.toHaveBeenCalled()
    expect(store.replaceText).not.toHaveBeenCalled()
  })

  it('file_result / skill_created / artifact_check / vision_* → Activities mit klaren Labels', () => {
    applyStreamEvent(
      { type: 'file_result', file_type: 'pdf', path: '/tmp/a.pdf', label: '📄 PDF: a.pdf' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: '📄 PDF: a.pdf',
      status: 'done',
      path: '/tmp/a.pdf',
      fileType: 'pdf',
    })
    applyStreamEvent(
      { type: 'skill_created', skill: { name: 's1', trigger: '/s1', description: 'd' } },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Skill erstellt: s1',
      status: 'done',
      detail: 'd',
    })
    applyStreamEvent(
      {
        type: 'artifact_check',
        artifact_type: 'csv',
        status: 'ok',
        path: '/tmp/a.csv',
        warnings: [],
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Check: csv',
      status: 'done',
      detail: '/tmp/a.csv',
    })
    applyStreamEvent({ type: 'vision_learning', target: 'chart' }, store)
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Lernt Bild-Erkennung: chart',
      status: 'running',
    })
    applyStreamEvent({ type: 'vision_learned_success', target: 'chart' }, store)
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Bild-Erkennung gelernt: chart',
      status: 'done',
    })
  })

  it('model_info + swarm_done = No-Ops (keine Store-Action)', () => {
    applyStreamEvent({ type: 'model_info', tier: 'offline', model: 'gemma4:e4b' }, store)
    applyStreamEvent(
      { type: 'swarm_done', swarm_id: 'sw-1', agent_count: 2, final: 'fertig' },
      store,
    )
    // Not a single store action
    const calls = [
      store.startTurn,
      store.appendChunk,
      store.appendThinking,
      store.replaceText,
      store.upsertToolCall,
      store.upsertActivity,
      store.resolveSandbox,
      store.markStreamError,
      store.setReflecting,
      store.setRevising,
      store.setQualityCheck,
      store.finishTurn,
    ].filter((m) => m.mock.calls.length > 0)
    expect(calls).toHaveLength(0)
  })

  it('usage → markLastUsage mit der gemessenen Bilanz (N7/N8a); Welle 3: cached mit durchgereicht', () => {
    applyStreamEvent(
      {
        type: 'usage',
        usage: {
          prompt_tokens: 29154,
          completion_tokens: 170,
          total_tokens: 29324,
          prompt_tokens_details: { cached_tokens: 12840 },
        },
      },
      store,
    )
    expect(store.markLastUsage).toHaveBeenCalledTimes(1)
    expect(store.markLastUsage).toHaveBeenCalledWith({
      in: 29154,
      out: 170,
      cached: 12840,
    })
    expect(store.finishTurn).not.toHaveBeenCalled()
  })
})
