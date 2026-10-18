import { AlertTriangle, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { fileUrl } from '@/lib/api'
import { friendlyError } from '@/lib/errorText'
import { markSetupIntent } from '@/lib/setupGate'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ChatMessage as LegacyChatMessage } from '@/store/chatStore'
import CodeBlock from '../CodeBlock'
import { ToolReplayKader } from '../ToolReplayKader'
import { AgentActivityRows } from '../ActivityFeed'
import AskUserQuestionCard from '../AskUserQuestionCard'
import { parseAskUserQuestion } from '@/lib/askUserQuestion'
import PlanCard from '../PlanCard'
import { parsePlanCard } from '@/lib/planCardModel'
import MessageFileCard from '../artifacts/messageCard'
import { producedFiles } from '../artifacts/messageCard'
import { summarizeToolDiff } from '@/lib/diffSummaryModel'
import { useChatStore } from '@/store/chatStore'

interface AssistantExtrasProps {
  m: LegacyChatMessage
  onPickOption?: (answer: string) => void
  onRetry?: (id: string) => void
}

/** P3 tail of an assistant turn: activity rows, replay frame, ask/plan
 *  cards, diff summary, inline artifacts, produced files, error + retry. */
export function AssistantExtras({ m, onPickOption, onRetry }: AssistantExtrasProps) {
  const { t } = useTranslation()
  const isAssistant = m.role === 'assistant'
  return (
    <>
      {/* P3 : subagent/swarm rows stay visible even after
                  turn end ("Explore · Completed") — permanently below
                  the tool groups, a pure derivation from m.activities. */}
      {!m.streaming && <AgentActivityRows activities={m.activities} />}

      {/* N2: tool-replay frame — numbered steps of the turn from the
                  trajectory snapshot, a single row while collapsed. */}
      {!m.streaming && <ToolReplayKader message={m} />}

      {/* J6: structured option card when the answer carries an
                  AskUserQuestion JSON block (content or artifact code) */}
      {!m.streaming && isAssistant && onPickOption
        ? (() => {
            const askSpec = parseAskUserQuestion(
              [m.content ?? '', ...(m.artifacts ?? []).map((a) => a.content ?? '')].join('\n'),
            )
            return askSpec ? <AskUserQuestionCard spec={askSpec} onPick={onPickOption} /> : null
          })()
        : null}

      {/* Z16 (reference parity): plan card with an approve/modify gate,
                  shown while the answer streams so the steps are readable as they arrive. */}
      {isAssistant && onPickOption
        ? (() => {
            const planSpec = parsePlanCard(m.content ?? '')
            return planSpec ? (
              <PlanCard spec={planSpec} onPick={onPickOption} streaming={m.streaming} />
            ) : null
          })()
        : null}

      {/* M3 (reference parity): stat line per run —
                  "N files changed +A −D  ↶ Undo" as the last edge of the tools. */}
      {!m.streaming &&
        isAssistant &&
        (() => {
          const ds = summarizeToolDiff(m.tool_calls)
          if (!ds) return null
          const undo = () => {
            const st = useChatStore.getState()
            const sid = st.activeSessionId
            const cps = sid && st.checkpoints[sid]?.length ? st.checkpoints[sid] : []
            const last = cps[cps.length - 1]
            if (last) st.rollbackToCheckpoint(last.id)
          }
          // F-9: without checkpoints there is nothing to roll back to —
          // render the summary line without a lying Undo button.
          const snap = useChatStore.getState()
          const hasCheckpoints = !!(
            snap.activeSessionId && snap.checkpoints[snap.activeSessionId]?.length
          )
          return (
            <div
              data-testid="diff-summary-line"
              className="mt-2 flex items-center gap-2 text-ui-sm font-mono text-ink-soft"
            >
              <span data-testid="diff-summary-files">
                {t('agentPanel.diffFiles', { count: ds.files })}
              </span>
              <span data-testid="diff-summary-add" className="text-status-success/90">
                +{ds.additions}
              </span>
              <span data-testid="diff-summary-del" className="text-status-danger/90">
                -{ds.deletions}
              </span>
              {hasCheckpoints && (
                <button
                  type="button"
                  data-testid="diff-summary-undo"
                  onClick={undo}
                  aria-label={t('agentPanel.diffUndo')}
                  title={t('agentPanel.diffUndo')}
                  className="inline-flex items-center gap-1 rounded-md border border-hairline bg-canvas px-1.5 py-0.5 text-ui-xs text-ink-faint hover:text-foreground hover:border-brand/30 transition-colors"
                >
                  <RotateCcw className="h-3 w-3" aria-hidden="true" />
                  {t('agentPanel.diffUndo')}
                </button>
              )}
            </div>
          )
        })()}

      {/* 3b. F-01: detector artifacts inline (code always stays visible/copyable).
                  One without content is a file rather than a listing, and 3c reaches it. */}
      {(m.artifacts ?? [])
        .filter((a) => a.content)
        .map((a, i) => (
          <div key={a.id ?? `a-${i}`} className="mt-2">
            <div className="mb-1 flex items-center gap-1.5 text-ui-xs text-ink-soft">
              <span aria-hidden="true">📄</span>
              <span className="font-medium text-foreground/80">{a.filename}</span>
              {/* Detector fallback sets title = filename; legacy-persisted
                        sessions keep that shape, so dedup at render time. */}
              {a.title && a.title !== a.filename && (
                <span className="truncate opacity-70">{a.title}</span>
              )}
              {/* K1 (reference parity): context link (chat.openInPanel) inside the stream */}
              <button
                type="button"
                data-testid="artifact-open-panel"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent(PREVIEW_OPEN_EVENT, {
                      detail: { url: fileUrl(a.filename) },
                    }),
                  )
                }
                className="ml-auto rounded-md px-1.5 py-0.5 text-ink-faint hover:text-brand hover:bg-surface-interactive transition-colors"
                aria-label={t('chat.openInPanel')}
              >
                {t('chat.openInPanel')}
              </button>
            </div>
            <CodeBlock code={a.content} language={a.language} />
          </div>
        ))}

      {/* 3c. #93: every file this turn produced, reachable here. The pane
                  does not open itself to show them — the message carries the way in. */}
      {producedFiles(m).map((f) => (
        <MessageFileCard key={f.key} file={f} />
      ))}

      {/* 4. Error (+ G1.2 retry) */}
      {m.error && (
        <div className="mt-2 rounded-md border border-status-danger/20 bg-status-danger/10 p-2 text-ui-xs text-status-danger">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            {friendlyError(m.error, t)}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {onRetry && (
              <button
                onClick={() => onRetry(m.id)}
                className="flex items-center gap-1.5 min-h-6 max-lg:min-h-11 rounded-md border border-status-danger/30 px-2 py-1 text-ui-xs text-red-200 hover:bg-status-danger/20 transition-colors"
                aria-label={t('chat.retry')}
              >
                <RotateCcw className="h-3 w-3" />
                {t('chat.retry')}
              </button>
            )}
            <button
              type="button"
              data-testid="error-setup-engine"
              onClick={() => {
                markSetupIntent()
                window.location.hash = '#/setup'
              }}
              className="flex items-center gap-1 min-h-6 max-lg:min-h-11 rounded-md border border-status-danger/30 px-2 py-1 text-ui-xs text-red-200 hover:bg-status-danger/20 transition-colors"
            >
              {t('chat.setupEngine')}
            </button>
          </div>
        </div>
      )}
    </>
  )
}
