import { AlertTriangle, FileCode, History, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { fileUrl } from '@/lib/api'
import { friendlyError } from '@/lib/errorText'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ChatMessage as LegacyChatMessage } from '@/store/chatStore'
import AskUserQuestionCard from '../AskUserQuestionCard'
import { parseAskUserQuestion } from '@/lib/askUserQuestion'
import PlanCard from '../PlanCard'
import { parsePlanCard, parsePlanJson } from '@/lib/planCardModel'
import MessageFileCard from '../artifacts/messageCard'
import { producedFiles } from '../artifacts/messageCard'
import { claimsMissingImage } from '@/lib/artifactClaims'
import TurnProgressLine from './turnProgress'
import { summarizeToolDiff } from '@/lib/diffSummaryModel'
import { useChatStore } from '@/store/chatStore'

interface AssistantExtrasProps {
  m: LegacyChatMessage
  onPickOption?: (answer: string) => void
  onRetry?: (id: string) => void
}

/** Open a tab of the one right-side panel. The steps, the subagent rows and the
 *  changed-file list already live there, so the bubble keeps one link per fact. */
function openPanelTab(tab: 'trajectory' | 'git' | 'subagents') {
  window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab } }))
}

/** P3 tail of an assistant turn: the live progress line, ask/plan cards, the one
 *  run line (diff + replay), artifact pills, produced files, error + retry. */
export function AssistantExtras({ m, onPickOption, onRetry }: AssistantExtrasProps) {
  const { t } = useTranslation()
  const isAssistant = m.role === 'assistant'
  const hasSteps = Boolean(m.tool_calls?.length || m.blocks?.length)

  const diff = (() => {
    if (m.streaming || !isAssistant) return null
    const ds = summarizeToolDiff(m.tool_calls)
    if (!ds) return null
    const undo = () => {
      const st = useChatStore.getState()
      const sid = st.activeSessionId
      const cps = sid && st.checkpoints[sid]?.length ? st.checkpoints[sid] : []
      const last = cps[cps.length - 1]
      if (last) st.rollbackToCheckpoint(last.id)
    }
    const snap = useChatStore.getState()
    const hasCheckpoints = !!(
      snap.activeSessionId && snap.checkpoints[snap.activeSessionId]?.length
    )
    return { ds, undo, hasCheckpoints }
  })()

  return (
    <>
      {m.streaming && m.progress && !m.error && (
        <TurnProgressLine progress={m.progress} />
      )}

      {/* J6: structured option card when the answer carries an AskUserQuestion JSON block */}
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
            const planSpec = parsePlanCard(m.content ?? '') ?? parsePlanJson(m.content ?? '')
            return planSpec ? (
              <PlanCard spec={planSpec} onPick={onPickOption} streaming={m.streaming} />
            ) : null
          })()
        : null}

      {/* M3: one run line per turn. The counts open the review tab, the Undo rolls
                  back to the last checkpoint, Replay opens the trajectory tab. */}
      {!m.streaming && (diff || (isAssistant && hasSteps)) && (
        <div
          data-testid="diff-summary-line"
          className="mt-2 flex flex-wrap items-center gap-2 text-ui-sm font-mono text-ink-soft"
        >
          {diff && (
            <button
              type="button"
              data-testid="diff-summary-open"
              onClick={() => openPanelTab('git')}
              title={t('chat.openInPanel')}
              className="inline-flex items-center gap-2 rounded-md px-1 -mx-1 py-0.5 transition-colors hover:text-foreground hover:bg-surface-interactive"
            >
              <span data-testid="diff-summary-files">
                {t('agentPanel.diffFiles', { count: diff.ds.files })}
              </span>
              <span data-testid="diff-summary-add" className="text-status-success/90">
                +{diff.ds.additions}
              </span>
              <span data-testid="diff-summary-del" className="text-status-danger/90">
                -{diff.ds.deletions}
              </span>
            </button>
          )}
          {diff?.hasCheckpoints && (
            <button
              type="button"
              data-testid="diff-summary-undo"
              onClick={diff.undo}
              aria-label={t('agentPanel.diffUndo')}
              title={t('agentPanel.diffUndo')}
              className="inline-flex items-center gap-1 rounded-md border border-hairline bg-canvas px-1.5 py-0.5 text-ui-xs text-ink-faint hover:text-foreground hover:border-brand/30 transition-colors"
            >
              <RotateCcw className="h-3 w-3" aria-hidden="true" />
              {t('agentPanel.diffUndo')}
            </button>
          )}
          {isAssistant && hasSteps && (
            <button
              type="button"
              data-testid="replay-link"
              onClick={() => openPanelTab('trajectory')}
              title={t('agentPanel.tabTrajectory')}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-ui-xs text-ink-faint transition-colors hover:text-foreground hover:bg-surface-interactive"
            >
              <History className="h-3 w-3" aria-hidden="true" />
              {t('agentPanel.tabTrajectory')}
            </button>
          )}
        </div>
      )}

      {/* 2. Detector artifacts as one-line pills. The code itself stands in the
                  answer above; the pill is the way into the panel, not a second copy. */}
      {(m.artifacts ?? [])
        .filter((a) => a.content)
        .map((a, i) => (
          <div
            key={a.id ?? `a-${i}`}
            data-testid={`message-artifact-${a.id ?? i}`}
            className="mt-2 flex items-center gap-2 rounded-md border border-hairline bg-surface/60 px-2 py-1.5"
          >
            <FileCode className="h-3.5 w-3.5 shrink-0 text-brand/70" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-ui-xs text-foreground/85">
              {a.filename}
            </span>
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
              className="shrink-0 rounded-md px-1.5 py-0.5 text-ui-2xs font-medium text-brand-deep transition-colors hover:bg-brand/10"
              aria-label={t('chat.openInPanel')}
            >
              {t('chat.openInPanel')}
            </button>
          </div>
        ))}

      {/* 3c. #93: every file this turn produced, reachable here. The pane
                  does not open itself to show them — the message carries the way in. */}
      {producedFiles(m).map((f) => (
        <MessageFileCard key={f.key} file={f} />
      ))}

      {/* A claim is not an artifact. When the answer says it made an image and
                  the turn registered none, the message says so instead of letting the
                  sentence stand on its own. */}
      {!m.streaming && isAssistant && claimsMissingImage(m.content ?? '', producedFiles(m)) && (
        <div
          role="alert"
          data-testid="artifact-claim-warning"
          className="mt-2 flex items-center gap-2 rounded-md border border-status-warning/40 bg-status-warning/10 px-2 py-1.5 text-ui-xs text-foreground/85"
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-status-warning" aria-hidden="true" />
          {t('artifacts.claimWithoutArtifact')}
        </div>
      )}

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
          </div>
        </div>
      )}
    </>
  )
}
