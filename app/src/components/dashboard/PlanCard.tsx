import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  PLAN_EXECUTION_MODE,
  planAcceptTurn,
  renderPlanBlock,
  type PlanCardSpec,
} from '@/lib/planCardModel'
import { COMPOSER_MODES, modeShortLabel } from './chat/ComposerModeMenu'
import { useChatStore } from '@/store/chatStore'

interface PlanCardProps {
  spec: PlanCardSpec
  onPick: (answer: string) => void
  /** True while the answer is still arriving: the steps are shown, the gate stays shut. */
  streaming?: boolean
}

const STATUS_ICON: Record<string, string> = {
  done: '✓',
  active: '▸',
  pending: '○',
  failed: '!',
  cancelled: '–',
}

const STATUS_CLASS: Record<string, string> = {
  done: 'text-status-success',
  active: 'text-status-warning',
  failed: 'text-status-danger',
  cancelled: 'text-ink-faint',
  pending: 'text-ink-faint',
}

/**
 * The plan card (#92). The block it renders is the one core/ephe_plan.py writes and
 * app/src/lib/planCardModel.ts parses; the gate below is the user's answer to it.
 *
 * The two buttons belong to a draft. Once a step has moved, the plan is the record of a run
 * that is already happening, and Accept offered twice starts that run twice.
 */
export default function PlanCard({ spec, onPick, streaming = false }: PlanCardProps) {
  const { t } = useTranslation()
  const [accepted, setAccepted] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string[]>(() => spec.items.map((i) => i.text))

  const live = spec.items.some((i) => i.status !== 'pending')
  // A half-written line shortens a step and the next frame lengthens it (planCardModel.ts), so
  // the card is readable while the answer arrives. The gate stays shut until the block is whole:
  // Accept on a half-written plan would start a run over steps the model has not finished.
  const gateOpen = !live && !accepted && !streaming

  // The chip the user reads has to name the mode the plan runs in: the short title comes
  // from the same translated hint the mode menu uses, so card and chip cannot disagree.
  const executionMode = COMPOSER_MODES.find((m) => m.key === PLAN_EXECUTION_MODE)
  const executionLabel = executionMode
    ? modeShortLabel(executionMode, String(t(executionMode.hintKey)))
    : PLAN_EXECUTION_MODE

  /**
   * Accept is the exit from Plan mode, not a message into it. Plan mode is read-only by
   * contract (server/routes/chat.py::_mode_context), so the click has to do both halves
   * in one place: move the session's composer mode to the one that can write (visible on
   * the chip) and hand the plan back as the turn that executes it. The old prose alone
   * left the composer in `plan`, and the next turn answered that it still had no tools.
   */
  const accept = () => {
    const store = useChatStore.getState()
    if (store.activeSessionId) store.setSessionMode(store.activeSessionId, PLAN_EXECUTION_MODE)
    setAccepted(true)
    onPick(
      planAcceptTurn(
        String(t('chat.planAcceptMsg')),
        spec.items.map((i) => i.text),
      ),
    )
  }

  const sendEdit = () => {
    const titles = draft.map((d) => d.trim()).filter(Boolean)
    if (!titles.length) return
    onPick(`${String(t('chat.planEditMsg'))}\n\n${renderPlanBlock(titles)}`)
    setEditing(false)
  }

  return (
    <div
      className="mt-2 rounded-2xl glass-reading p-3 space-y-1.5"
      data-testid="plan-card"
      data-state={accepted ? 'accepted' : live ? 'running' : 'draft'}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-ui-sm font-medium text-brand/90">{t('chat.planTitle')}</p>
        <span data-testid="plan-progress" className="text-ui-sm font-mono text-ink-faint shrink-0">
          {`${spec.done}/${spec.total}`}
        </span>
      </div>

      {editing ? (
        <ol className="space-y-1" data-testid="plan-editor">
          {draft.map((title, i) => (
            <li key={`edit-${i}`} className="flex items-start gap-2">
              <span className="font-mono text-ui-xs text-ink-soft mt-1.5 shrink-0">{i + 1}.</span>
              <textarea
                data-testid={`plan-step-input-${i}`}
                aria-label={String(t('chat.planStepAria', { n: i + 1 }))}
                value={title}
                rows={1}
                onChange={(e) =>
                  setDraft((prev) => prev.map((p, j) => (j === i ? e.target.value : p)))
                }
                className="min-w-0 flex-1 resize-y rounded-lg bg-surface border border-hairline px-2 py-1 text-ui-xs text-foreground"
              />
            </li>
          ))}
          <li className="flex items-center gap-2 pt-0.5">
            <button
              type="button"
              data-testid="plan-edit-send"
              onClick={sendEdit}
              className="px-2.5 py-1 rounded-lg text-ui-xs font-medium bg-brand/20 text-brand border border-brand/20 hover:bg-brand/20 transition-colors"
            >
              {t('chat.planEditSend')}
            </button>
            <button
              type="button"
              data-testid="plan-edit-cancel"
              onClick={() => {
                setEditing(false)
                setDraft(spec.items.map((i) => i.text))
              }}
              className="px-2.5 py-1 rounded-lg text-ui-xs font-medium text-ink-faint hover:text-foreground transition-colors"
            >
              {t('chat.planEditCancel')}
            </button>
          </li>
        </ol>
      ) : (
        <ol className="space-y-1">
          {spec.items.map((item, i) => (
            <li
              key={`${item.text}-${i}`}
              className="flex items-start gap-2 text-ui-xs text-foreground/80"
              data-testid={`plan-item-${i}`}
              data-status={item.status}
            >
              <span
                aria-hidden="true"
                className={`shrink-0 font-mono ${STATUS_CLASS[item.status] ?? 'text-ink-faint'}`}
              >
                {STATUS_ICON[item.status] ?? '○'}
              </span>
              <span
                className={`min-w-0 ${item.status === 'done' ? 'line-through decoration-2 decoration-mist/80 text-ink-soft' : ''}`}
              >
                <span className="font-mono text-ink-soft mr-1">{i + 1}.</span>
                {item.text}
              </span>
            </li>
          ))}
        </ol>
      )}

      {gateOpen && (
        <div className="flex items-center gap-2 pt-0.5">
          <button
            type="button"
            data-testid="plan-accept"
            onClick={accept}
            className="px-2.5 py-1 rounded-lg text-ui-xs font-medium bg-brand/20 text-brand border border-brand/20 hover:bg-brand/20 transition-colors"
          >
            {t('chat.planAccept')}
          </button>
          <button
            type="button"
            data-testid="plan-edit"
            onClick={() => setEditing(true)}
            className="px-2.5 py-1 rounded-lg text-ui-xs font-medium bg-surface text-foreground/80 border border-hairline hover:bg-surface transition-colors"
          >
            {t('chat.planEdit')}
          </button>
        </div>
      )}

      {accepted && (
        <p className="pt-0.5 text-ui-xs text-status-success" data-testid="plan-accepted">
          {t('chat.planAccepted', { mode: executionLabel })}
        </p>
      )}
      {live && !editing && (
        <p className="pt-0.5 text-ui-xs text-ink-faint" data-testid="plan-running-note">
          {t('chat.planRunning')}
        </p>
      )}
    </div>
  )
}
