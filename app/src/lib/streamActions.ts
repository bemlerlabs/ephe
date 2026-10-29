/**
 * Ephe — PWA chat UX plan, task C1: stream event → store action mapping
 *
 * Event contract (anchored in server/routes/chat.py + core/swarm_state.py):
 *   - thinking_start       → open the thinking phase (startTurn)
 *   - chunk                → append content (appendChunk)
 *   - replace_text         → replace content (revision, replaceText)
 *   - activity             → upsert the tool/phase activity (upsertActivity)
 *   - tool_start/tool_done → upsert the tool call (upsertToolCall)
 *   - phase                → upsert activity
 *   - quality_check        → transient qualityCheck phase
 *   - reflect              → transient reflecting phase
 *   - revision             → transient revising phase (content stays)
 *   - artifact / file_result → activity (label/path)
 *   - plan                 → setPlan (the turn's steps and their state, #92)
 *   - goal_start           → beginGoal (the goal loop's own state: goal, check, budget)
 *   - goal_turn/goal_check → advanceGoal (the round it is in, that round's verdict)
 *   - swarm_status / swarm_created / swarm_agent_started / swarm_agent_done
 *                            → activity (agent feed)
 *   - subagent_started / subagent_tool / subagent_done
 *                            → activity (R36-S: spawn_agent helper feed)
 *   - skill_created        → activity
 *   - model_info / vision_learning / vision_learned_success
 *                            → no-op (handled by the UI, no message mutation)
 *   - swarm_done            → activity only when it carries measured tokens

 *   - sandbox_confirm      → resolveSandbox (token as tool.description)
 *   - ask_user             → resolveAsk (G1: the run is paused on this question)
 *   - ask_timeout          → markAskTimedOut (G1: nobody answered, the run went on)
 *   - error                → markStreamError
 *   - done                 → finishTurn
 *
 * Pure mapping (get/set injected) → unit-testable without zustand.
 */
import type { StreamEvent } from '@/types'
import { planFromEvent } from '@/lib/planCardModel'
import type { ChatStore } from '@/store/chatStore'

type Store = Pick<
  ChatStore,
  | 'startTurn'
  | 'appendChunk'
  | 'appendThinking'
  | 'replaceText'
  | 'upsertToolCall'
  | 'upsertActivity'
  | 'setTurnId'
  | 'setProgress'
  | 'attachArtifact'
  | 'setPlan'
  | 'beginGoal'
  | 'advanceGoal'
  | 'resolveSandbox'
  | 'resolveAsk'
  | 'markAskTimedOut'
  | 'markStreamError'
  | 'markLastUsage'
  | 'markBudgetReached'
  | 'setReflecting'
  | 'setRevising'
  | 'setQualityCheck'
  | 'finishTurn'
  | 'beginHelperChat'
  | 'stepHelperChat'
  | 'endHelperChat'
>
import { serverErrorText } from './serverError'

const shortTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))

/** "1.2k in / 240 out" from what the engine reported; empty when it reported none. */
function tokenNote(tokensIn?: number, tokensOut?: number): string {
  const parts: string[] = []
  if (tokensIn) parts.push(`${shortTokens(tokensIn)} in`)
  if (tokensOut) parts.push(`${shortTokens(tokensOut)} out`)
  return parts.length > 0 ? `${parts.join(' / ')} tok` : ''
}

export function applyStreamEvent(event: StreamEvent, store: Store): void {
  switch (event.type) {
    case 'thinking_start':
      // thinking_start always arrives before the first chunk; we start the turn
      // here so the message exists when the chunk arrives.
      store.startTurn()
      break

    case 'thinking_chunk':
      // AI-client parity: stream reasoning text → thinking block (collapsed)
      store.appendThinking(event.data)
      break

    case 'chunk':
      store.appendChunk(event.data)
      break

    case 'replace_text':
      store.replaceText(event.text)
      break

    case 'activity':
      store.upsertActivity({
        label: event.cmd,
        status: event.status === 'done' ? 'done' : event.status === 'failed' ? 'failed' : 'running',
      })
      break

    case 'tool_start':
      store.upsertToolCall({
        name: event.tool,
        args: event.args,
        status: 'pending',
      })
      break

    case 'tool_done':
      store.upsertToolCall({
        name: event.tool,
        result: event.result,
        // w10-12 + S21: 'failed' is the server's outcome for a call that did not
        // succeed. The approval refusal keeps its own name — its result opens with
        // DENIAL_PREFIX — while a failed fetch or a tool error shows as Failed with
        // its reason. A frame without the field (older backends, replays) stays
        // 'completed' as before.
        status:
          event.status === 'failed'
            ? String(event.result ?? '').startsWith('[TOOL-DENIED]')
              ? 'denied'
              : 'failed'
            : 'completed',
        ...(event.duration_ms !== undefined ? { durationMs: event.duration_ms } : {}),
        ...(event.reason_code !== undefined ? { reasonCode: event.reason_code } : {}),
        ...(event.reason_params !== undefined ? { reasonParams: event.reason_params } : {}),
        ...(event.sha256 !== undefined ? { sha256: event.sha256 } : {}),
      })
      break

    case 'stdout':
      // K3 Z07: live tail — the store appends the chunks to the call
      // (growing pre block inside the expanded detail).
      store.upsertToolCall({
        name: event.tool,
        stdout: event.data,
        status: 'pending',
      })
      break

    case 'phase':
      store.upsertActivity({
        label: event.name,
        status: event.status === 'done' ? 'done' : event.status === 'failed' ? 'failed' : 'running',
      })
      break

    case 'gap':
      // Wave 7: knowledge-gap feed — one activity per detected gap.
      store.upsertActivity({
        label: `Wissenslücke: ${event.topic} — ${event.sources.length > 0 ? `${event.sources.length} Quelle(n) gedeckt` : event.status}`,
        status: event.status === 'failed' ? 'failed' : 'done',
      })
      break

    case 'quality_check':
      store.setQualityCheck(event.status === 'running')
      break

    case 'reflect':
      store.setReflecting(event.status === 'running')
      break

    case 'revision':
      store.setRevising(true)
      break

    case 'artifact': {
      // F-01: attach the artifact content to the message (inline render as CodeBlock).
      // The activity stays as a feed entry — the label uses the real file name.
      const art = event.artifact as {
        id?: string
        artifact_type?: string
        content?: string
        language?: string
        title?: string
        filename?: string
      }
      store.attachArtifact({
        id: art.id ?? crypto.randomUUID(),
        artifact_type: art.artifact_type ?? 'code_other',
        content: art.content ?? '',
        language: art.language ?? 'text',
        title: art.title ?? art.filename ?? 'Artifact',
        filename: art.filename ?? 'artifact.txt',
      })
      store.upsertActivity({
        label: `Artifact: ${art.filename ?? art.artifact_type ?? 'datei'}`,
        status: 'done',
      })
      break
    }

    case 'plan': {
      // #92: the steps arrive as their own frame, so the card is on screen while the
      // answer is still streaming and each state change repaints it.
      const spec = planFromEvent(event.steps ?? [])
      if (spec) store.setPlan(spec)
      break
    }

    case 'goal_start':
      // The goal loop's own three values, before its first model call: the surface
      // shows the goal the loop works toward instead of guessing it from a message.
      store.beginGoal(event.goal, event.check, event.max_turns)
      break

    case 'goal_turn':
      store.advanceGoal(event.turn)
      break

    case 'goal_check':
      store.advanceGoal(event.turn, event.ok)
      break

    case 'budget':
      // QD-015 Z2: the cap end carries the continuation offer — the button
      // reads the same numbers the server counted with.
      store.markBudgetReached(event.cap, event.extra)
      break

    case 'artifact_check':
      store.upsertActivity({
        label: `Check: ${event.artifact_type}`,
        status: event.status === 'ok' ? 'done' : event.status === 'failed' ? 'failed' : 'running',
        detail: event.warnings.length > 0 ? event.warnings.join(', ') : event.path,
      })
      break

    case 'turn':
      // A3: the id belongs on the message, so the workbench can show back
      // which request a file was born from.
      store.setTurnId(event.turn_id)
      break

    case 'progress':
      store.setProgress({
        tool: event.tool,
        round: event.round,
        roundCap: event.round_cap,
        phase: event.phase,
        elapsedMs: event.elapsed_ms,
        query: event.query,
        providers: event.providers,
        status: event.status,
      })
      break

    case 'file_result':
      store.upsertActivity({
        label: event.label ?? `${event.file_type}: ${event.path}`,
        status: 'done',
        path: event.path,
        fileType: event.file_type,
        artifactId: event.id || undefined,
      })
      break

    case 'swarm_status':
      store.upsertActivity({
        label: event.message,
        status: 'running',
      })
      break

    case 'swarm_created':
      store.upsertActivity({
        label: `Swarm: ${event.agents.length} Agents`,
        status: 'done',
        detail: event.agents.map((a) => `${a.role} · ${a.model}`).join(', '),
      })
      break

    case 'swarm_agent_started':
      store.upsertActivity({
        label: `Agent ${event.agent_id}`,
        status: 'running',
        // QD-016 C1: the card names the model that runs it; the old frame
        // carried the task alone and the deck could not show the wiring.
        detail: event.model ? `${event.model} · ${event.subtask}` : event.subtask,
      })
      break

    case 'swarm_agent_done':
      store.upsertActivity({
        label: `Agent ${event.agent_id}`,
        status: event.status === 'error' ? 'failed' : 'done',
        detail: [event.summary, tokenNote(event.tokens_in, event.tokens_out)]
          .filter(Boolean)
          .join(' · '),
      })
      break

    case 'swarm_done': {
      // The final text arrives as a chunk. The frame's token record is the one
      // number the feed can state honestly: agents' own context next to the
      // brief the merge step read. No record, no line.
      const tokens = event.tokens
      if (tokens && tokens.agent_in > 0 && tokens.merge_in > 0) {
        const saved = Math.max(0, 100 - Math.round((tokens.merge_in / tokens.agent_in) * 100))
        store.upsertActivity({
          label: 'Swarm envelope',
          status: 'done',
          detail: `${shortTokens(tokens.agent_in)} → ${shortTokens(tokens.merge_in)} tok (−${saved}%)`,
        })
      }
      break
    }

    case 'subagent_started':
      // R36-S: delegated helper — one activity per agent_id (label key);
      // the tool/done events upsert the same activity (live progress).
      store.upsertActivity({
        label: `SubAgent ${event.agent_id} (${event.role})`,
        status: 'running',
        detail: event.task,
      })
      // Visibility wave: the same run gets its own chat. Without
      // chat_session_id (older server) it stays at the activity line.
      if (event.chat_session_id) {
        store.beginHelperChat({
          chatSessionId: event.chat_session_id,
          agentId: event.agent_id,
          parentSession: event.parent_session,
          role: event.role,
          description: event.description,
          task: event.task,
        })
      }
      break

    case 'subagent_tool':
      store.upsertActivity({
        label: `SubAgent ${event.agent_id}`,
        status: 'running',
        // C2: the gate's verdict rides on the same line, so a refused or
        // approved write is visible on the card instead of only in the audit.
        detail: event.gate
          ? `${event.gate} · ${event.tool}: ${event.args_preview}`
          : `${event.tool}: ${event.args_preview}`,
      })
      if (event.chat_session_id) {
        store.stepHelperChat({
          chatSessionId: event.chat_session_id,
          agentId: event.agent_id,
          tool: event.tool,
          argsPreview: event.args_preview,
        })
      }
      break

    case 'steer':
      // D2: the direction change appears where the run is read. For an agent
      // the line is keyed to that card; for the whole run it stands alone.
      store.upsertActivity({
        label: event.agent_id ? `Steer ${event.agent_id}` : event.msg,
        status: event.status === 'unlanded' ? 'failed' : 'done',
        detail: event.text,
      })
      break

    case 'subagent_done': {
      const failed = event.status === 'timeout' || event.status === 'error'
      store.upsertActivity({
        label: `SubAgent ${event.agent_id}`,
        status: failed ? 'failed' : 'done',
        detail: event.summary,
      })
      if (event.chat_session_id) {
        store.endHelperChat({
          chatSessionId: event.chat_session_id,
          agentId: event.agent_id,
          status: event.status,
          report: event.report,
          summary: event.summary,
          parentSession: event.parent_session,
        })
      }
      break
    }

    case 'skill_created':
      store.upsertActivity({
        label: `Skill erstellt: ${event.skill.name}`,
        status: 'done',
        detail: event.skill.description,
      })
      break

    case 'model_info':
      // Tier info — handled by the UI (badge), no message mutation
      break

    case 'vision_learning':
      store.upsertActivity({
        label: `Lernt Bild-Erkennung: ${event.target}`,
        status: 'running',
      })
      break

    case 'vision_learned_success':
      store.upsertActivity({
        label: `Bild-Erkennung gelernt: ${event.target}`,
        status: 'done',
      })
      break

    case 'sandbox_confirm':
      store.resolveSandbox(event.token, event.tool, event.args, event.rememberable, event.diff)
      break

    case 'ask_user':
      // G1: the ask gate's frame. The run waits on the server until an answer lands
      // through POST /api/ask/answer — nothing is sent from here on its own.
      store.resolveAsk({
        token: event.token,
        question: event.question,
        options: event.options ?? [],
        recommendation: event.recommendation,
        multiSelect: event.multiSelect,
        timeoutS: event.timeout_s,
        defaultAnswer: event.default,
      })
      break

    case 'ask_timeout':
      // Nobody answered: the same run continued on its stated default.
      store.markAskTimedOut(event.token)
      break

    case 'error':
      // A refusal that carries its reason is answered from the bundle, so the reader gets the
      // sentence in the language they set; `msg` stays the fallback for every older server.
      store.markStreamError(
        serverErrorText(event.reason_code, event.reason_params, event.msg),
        event.reason_code,
      )
      break

    case 'usage': {
      // N7/N8a: the real ledger into the store — the StatusBar chip showed it
      // while the session's server mirror was still empty.
      // Wave 3: measured cache hits travel along (cost/cache chip).
      const u = event.usage
      store.markLastUsage({
        in: u.prompt_tokens ?? 0,
        out: u.completion_tokens ?? 0,
        cached: u.prompt_tokens_details?.cached_tokens ?? 0,
      })
      break
    }

    case 'done':
      store.finishTurn()
      break

    default: {
      // Exhaustiveness proof: breaks tsc when a new event shows up in the
      // union without being handled here.
      const _exhaustive: never = event
      void _exhaustive
    }
  }
}
