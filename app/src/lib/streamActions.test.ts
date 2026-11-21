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
    markSolInsight: vi.fn(),
    markCitationCheck: vi.fn(),
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

describe('applyStreamEvent: the event to store-action mapping', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('thinking_start starts the turn before the first chunk', () => {
    applyStreamEvent({ type: 'thinking_start' }, store)
    expect(store.startTurn).toHaveBeenCalledTimes(1)
  })

  it('thinking_chunk appends thinking with the exact data (AI client parity)', () => {
    applyStreamEvent({ type: 'thinking_chunk', data: 'Ich überlege…' }, store)
    expect(store.appendThinking).toHaveBeenCalledTimes(1)
    expect(store.appendThinking).toHaveBeenCalledWith('Ich überlege…')
    // Thinking chunks must NOT enter the content-chunk flow (appendChunk)
    expect(store.appendChunk).not.toHaveBeenCalled()
  })

  it('chunk appends with the exact data', () => {
    applyStreamEvent({ type: 'chunk', data: 'Hallo ' }, store)
    applyStreamEvent({ type: 'chunk', data: 'Welt' }, store)
    expect(store.appendChunk).toHaveBeenNthCalledWith(1, 'Hallo ')
    expect(store.appendChunk).toHaveBeenNthCalledWith(2, 'Welt')
  })

  it('replace_text rewrites the whole content (revision)', () => {
    applyStreamEvent({ type: 'replace_text', text: 'sauber' }, store)
    expect(store.replaceText).toHaveBeenCalledWith('sauber')
  })

  it('activity upserts with the cmd as label and a status mapping', () => {
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

  it('phase upserts an activity with the name as label', () => {
    applyStreamEvent({ type: 'phase', name: 'Recherche', status: 'running' }, store)
    expect(store.upsertActivity).toHaveBeenCalledWith({
      label: 'Recherche',
      status: 'running',
    })
  })

  it('quality_check sets the check true only while the status runs', () => {
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

  it('citation_check → markCitationCheck (the verdict lands on the answer)', () => {
    applyStreamEvent(
      {
        type: 'citation_check',
        run_id: 'r_1',
        checked: 3,
        verified: 2,
        unverified: ['The moon is made of cheese.'],
      },
      store,
    )
    expect(store.markCitationCheck).toHaveBeenCalledWith({
      runId: 'r_1',
      checked: 3,
      verified: 2,
      unverified: ['The moon is made of cheese.'],
    })
  })

  it('sandbox_confirm resolves with token, tool, args and an optional diff', () => {
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

  it('sandbox_confirm hands the diff as the 5th argument to resolveSandbox', () => {
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

  it('error marks the stream error; only the message ends, finishTurn waits for done', () => {
    applyStreamEvent({ type: 'error', msg: 'Ollama nicht erreichbar' }, store)
    expect(store.markStreamError).toHaveBeenCalledWith('Ollama nicht erreichbar', undefined)
  })

  it('done → finishTurn', () => {
    applyStreamEvent({ type: 'done' }, store)
    expect(store.finishTurn).toHaveBeenCalledTimes(1)
  })

  it('swarm events become activities (the agent feed)', () => {
    applyStreamEvent(
      { type: 'swarm_status', phase: 'planning', message: '🐝 Swarm V2 started' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: '🐝 Swarm V2 started',
      status: 'running',
    })
    applyStreamEvent(
      {
        type: 'swarm_created',
        swarm_id: 'sw-1',
        agents: [
          { agent_id: 'a1', role: 'researcher', model: 'gemma4:e4b', task_spec_hash: 'h1' },
          { agent_id: 'a2', role: 'researcher', model: 'gemma4:e4b', task_spec_hash: 'h2' },
        ],
        model: 'gemma4:e4b',
      },
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

  it('R36-S: subagent events become activities, one feed entry per agent_id', () => {
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

  it('F-01: artifact attaches the content to the message plus an activity with the name', () => {
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

  it('file_result, skill_created, artifact_check and vision events get clear labels', () => {
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

  it('model_info and swarm_done are no-ops without a store action', () => {
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

  it('usage marks the measured balance (N7/N8a); wave 3 passes cached along', () => {
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
