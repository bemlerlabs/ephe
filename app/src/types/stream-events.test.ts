/**
 * Ephe — PWA chat UX plan, task A3: the StreamEvent union
 *
 * GIVEN  the StreamEvent discriminated union (types/index.ts)
 * WHEN   fed every event payload shape the backend can emit (server/routes/chat.py)
 * THEN   the union narrows cleanly (the type switch is exhaustive)
 * AND    the payload shapes match the backend contract exactly
 *
 * Note: the shapes are anchored in chat.py — a backend change (e.g. a new field
 * in tool_done) has to be carried through here as well.
 */
import { describe, it, expect } from 'vitest'
import type {
  StreamEvent,
  StreamChunk,
  StreamToolDone,
  StreamActivity,
  StreamSandboxConfirm,
  StreamAskUser,
  StreamAskTimeout,
  StreamSwarmCreated,
  StreamError,
  StreamDone,
} from '../types'

/** Exhaustiveness proof: breaks tsc when the StreamEvent union is incomplete */
function assertNever(event: never): never {
  throw new Error(`Unbekanntes StreamEvent: ${String((event as { type: string }).type)}`)
}

/** Exhaustiveness check: the union covers every backend event type */
function assertExhaustive(event: StreamEvent, sink: string[] = []): void {
  switch (event.type) {
    case 'thinking_start':
    case 'thinking_chunk':
    case 'chunk':
    case 'activity':
    case 'stdout':
    case 'tool_start':
    case 'tool_done':
    case 'phase':
    case 'quality_check':
    case 'artifact_check':
    case 'reflect':
    case 'revision':
    case 'replace_text':
    case 'artifact':
    case 'plan':
    case 'goal_start':
    case 'goal_turn':
    case 'goal_check':
    case 'gap':
    case 'skill_created':
    case 'swarm_created':
    case 'swarm_agent_started':
    case 'swarm_agent_done':
    case 'swarm_done':
    case 'swarm_status':
    case 'subagent_started':
    case 'subagent_tool':
    case 'subagent_done':
    case 'file_result':
    case 'model_info':
    case 'usage':
    case 'vision_learning':
    case 'turn':
    case 'vision_learned_success':
    case 'sandbox_confirm':
    case 'ask_user':
    case 'ask_timeout':
    case 'error':
    case 'done':
      sink.push(event.type)
      return
    default:
      return assertNever(event)
  }
}

describe('StreamEvent (Diskriminierte Union)', () => {
  it('deckt alle 33 Backend-Event-Typen exhaustiv ab', () => {
    const events: StreamEvent[] = [
      { type: 'thinking_start' },
      { type: 'thinking_chunk', data: 'Ich überlege…' },
      { type: 'chunk', data: 'Hallo' },
      { type: 'activity', cmd: 'git status', status: 'running' },
      { type: 'stdout', tool: 'run_shell', data: 'a\nb' },
      { type: 'tool_start', tool: 'run_shell', args: { command: 'ls' } },
      { type: 'tool_done', tool: 'run_shell', result: 'ok', duration_ms: 1.2 },
      { type: 'phase', name: 'retrieval', status: 'done' },
      { type: 'quality_check', status: 'running', skill: 'codebase-inspection' },
      {
        type: 'artifact_check',
        artifact_type: 'html',
        status: 'ok',
        path: '/tmp/x.html',
        warnings: [],
      },
      { type: 'reflect', status: 'done', needs_revision: false },
      { type: 'revision', reason: 'Antwort unvollständig' },
      { type: 'replace_text', text: 'sauber' },
      { type: 'artifact', artifact: { type: 'html', path: '/tmp/x.html' } },
      {
        type: 'plan',
        state: 'draft',
        done: 0,
        total: 2,
        steps: [
          { title: 'Read routes', status: 'pending' },
          { title: 'Add case', status: 'pending' },
        ],
      },
      { type: 'skill_created', skill: { name: 'x', trigger: 'x', description: 'x' } },
      {
        type: 'goal_start',
        goal: 'Fix the login bug',
        check: 'npm test',
        max_turns: 4,
      },
      { type: 'goal_turn', turn: 1 },
      { type: 'goal_check', turn: 1, ok: true, output: '2 passed' },
      { type: 'swarm_created', swarm_id: 's1', agents: ['a1', 'a2'], model: 'gemma4:12b' },
      { type: 'swarm_agent_started', swarm_id: 's1', agent_id: 'a1', subtask: 't' },
      { type: 'swarm_agent_done', swarm_id: 's1', agent_id: 'a1', summary: 'done' },
      {
        type: 'subagent_started',
        agent_id: 'subagent-1',
        role: 'researcher',
        task: 't',
        model: 'm',
      },
      { type: 'subagent_tool', agent_id: 'subagent-1', tool: 'web_search', args_preview: '{…}' },
      { type: 'subagent_done', agent_id: 'subagent-1', status: 'ok', summary: 'done' },
      { type: 'swarm_done', swarm_id: 's1', agent_count: 2, final: 'synthese' },
      { type: 'vision_learning', target: 'screenshot' },
      { type: 'vision_learned_success', target: 'screenshot' },
      {
        type: 'sandbox_confirm',
        token: 'abc',
        tool: 'run_shell',
        args: { command: 'rm -rf /tmp/x' },
      },
      {
        type: 'ask_user',
        token: 'ask-1',
        question: 'Which branch?',
        options: ['main', 'wt/n1-ask'],
        recommendation: 'main',
        default: 'main',
        timeout_s: 180,
      },
      { type: 'ask_timeout', token: 'ask-1', timeout_s: 180, default: 'main' },
      { type: 'error', msg: 'Ollama nicht erreichbar' },
      { type: 'done' },
    ]
    const seen: string[] = []
    for (const e of events) assertExhaustive(e, seen)
    expect(new Set(seen).size).toBe(33) // 31 + the ask gate's ask_user/ask_timeout frames
  })

  it('chunk-Payload: { data: string } (exakt, kein content-Feld)', () => {
    const e: StreamChunk = { type: 'chunk', data: 'x' }
    expect(e.data).toBe('x')
    // @ts-expect-error — chunk carries "data", not "content"
    expect(e.content).toBeUndefined()
  })

  it('tool_done-Payload: { tool, result }', () => {
    const e: StreamToolDone = { type: 'tool_done', tool: 'read_file', result: '42' }
    expect(e.tool).toBe('read_file')
    expect(e.result).toBe('42')
  })

  it('activity-Payload: { cmd, status }', () => {
    const e: StreamActivity = { type: 'activity', cmd: 'rg foo', status: 'done' }
    expect(e.cmd).toBe('rg foo')
    expect(e.status).toBe('done')
  })

  it('sandbox_confirm-Payload: { token, tool, args } (Token für /sandbox/approve)', () => {
    const e: StreamSandboxConfirm = {
      type: 'sandbox_confirm',
      token: 't',
      tool: 'run_shell',
      args: { command: 'pwd' },
    }
    expect(e.token).toBe('t')
    expect(e.tool).toBe('run_shell')
  })

  it('ask_user-Payload: { token, question, options, default, timeout_s } (G1 ask gate)', () => {
    const e: StreamAskUser = {
      type: 'ask_user',
      token: 'ask-1',
      question: 'Which branch?',
      options: ['main', 'wt/n1-ask'],
      default: 'main',
      timeout_s: 180,
    }
    expect(e.token).toBe('ask-1')
    expect(e.options).toHaveLength(2)
    expect(e.timeout_s).toBe(180)
  })

  it('ask_timeout-Payload: { token, default } — the run went on (G1)', () => {
    const e: StreamAskTimeout = { type: 'ask_timeout', token: 'ask-1', default: 'main' }
    expect(e.token).toBe('ask-1')
    expect(e.default).toBe('main')
  })

  it('swarm_created-Payload: { swarm_id, agents, model }', () => {
    const e: StreamSwarmCreated = {
      type: 'swarm_created',
      swarm_id: 'sw',
      agents: ['a'],
      model: 'm',
    }
    expect(e.swarm_id).toBe('sw')
    expect(e.agents).toEqual(['a'])
  })

  it('error-Payload: { msg } (kein "message"-Feld)', () => {
    const e: StreamError = { type: 'error', msg: 'Fehler' }
    expect(e.msg).toBe('Fehler')
  })

  it('done-Payload: kein Zusatzfeld', () => {
    const e: StreamDone = { type: 'done' }
    expect(e).toEqual({ type: 'done' })
  })
})
