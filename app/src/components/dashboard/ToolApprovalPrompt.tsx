import { useEffect, useRef, useState } from 'react'
import { ShieldAlert, Check, ShieldCheck, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import DiffView from './DiffView'
import { gateIsAnswerable } from '@/lib/sandboxGate'
import type { ToolCall } from '@/store/chatStore'

/**
 * Inline tool-approval banner (PWA-Chat-UX-Plan, task B5).
 * Appears when the backend sends a sandbox_confirm event
 * (tool call in status 'waiting', `approval.token` = sandbox token).
 *
 * The gate carries its own state (see `ApprovalGate`): an answered or expired gate
 * renders no action row at all, so an answered card cannot be clicked a second time
 * and reads as answered. `primary` marks the oldest open gate — the one that takes
 * focus and speaks as an alertdialog; the rest of a queue of open gates are ordinary
 * labelled groups, so a second card does not steal the focus of the first.
 *
 * D1 a11y:
 * - role="alertdialog" + aria-label (screen-reader announcement) on the primary card
 * - initial focus on Deny (conservative: approving needs an
 *   explicit Tab/click — no accidental approve)
 * - focus trap: Tab/Shift+Tab cycle inside the action row, whatever it holds
 * - Esc = escape hatch → onDeny
 *
 * Architecture: renders UI only and calls onApprove/onDeny — the API call
 * (POST /api/sandbox/approve) belongs in the wiring (task C1).
 */
/** What a closed gate says about itself: the outcome, and whose hand closed it. An
 *  expiry names neither, because there was neither — the window ran out and nothing
 *  ran. That line is the difference between "you denied this" and "nobody answered". */
function outcomeWord(tool: ToolCall, t: (key: string) => string): string {
  const gate = tool.approval
  if (!gate) {
    // A transcript written before the gate record holds only the row's own status.
    return tool.status === 'denied'
      ? t('chat.toolApproval.deniedByYou')
      : tool.status === 'approved'
        ? t('chat.toolApproval.allowedByYou')
        : t('chat.toolApproval.expiredOutcome')
  }
  // The gate's own state decides which of the two closes it was; the row's status
  // field carries only that a close happened, so reading it here would turn a token
  // the server had already spent into "nobody answered".
  if (gate.state === 'expired') return t('chat.toolApproval.expiredOutcome')
  if (gate.closedBy === 'server') return t('chat.toolApproval.spentOutcome')
  if (gate.outcome === 'denied') return t('chat.toolApproval.deniedByYou')
  return gate.closedBy === 'companion'
    ? t('chat.toolApproval.allowedByCompanion')
    : t('chat.toolApproval.allowedByYou')
}

export default function ToolApprovalPrompt({
  tool,
  rememberable = false,
  primary = true,
  onApprove,
  onDeny,
  onDenyWithCorrection,
}: {
  tool: ToolCall
  rememberable?: boolean
  /** The oldest open gate of the turn: the one that takes focus and announces. */
  primary?: boolean
  onApprove: (remember?: boolean) => void
  onDeny: () => void
  /** E2: refuse and say what to do instead; the wiring denies, then sends it. */
  onDenyWithCorrection?: (text: string) => void
}) {
  const { t } = useTranslation()
  const [correction, setCorrection] = useState('')
  const [asking, setAsking] = useState(false)
  // The single answer to "may this card act?": the gate's own state, plus its window.
  // Nothing below this line offers an action when it is false.
  const open = gateIsAnswerable(tool)
  const submitting = tool.approval?.state === 'submitting'
  const outcome = open || submitting ? null : outcomeWord(tool, t)
  const submitCorrection = () => {
    const text = correction.trim()
    if (!text) return
    setCorrection('')
    setAsking(false)
    onDenyWithCorrection?.(text)
  }
  const argsPreview = JSON.stringify(tool.args ?? {})
  // M4 (blast radius): the directly affected values (path/URL/amount) as one
  // compact line — the user immediately sees what the action touches.
  const blast = ['path', 'file', 'file_path', 'url', 'command', 'dir', 'cwd']
    .map((k) =>
      tool.args && k in tool.args
        ? `${k}=${String((tool.args as Record<string, unknown>)[k])}`
        : null,
    )
    .filter((x): x is string => x != null)
    .join('  ·  ')
  const dialogRef = useRef<HTMLDivElement>(null)

  // Initial focus on Deny (conservative) + Tab focus trap + Esc. A closed gate has no
  // action row to trap, and a card that is not the primary one never takes focus from
  // the gate the reader is being asked about.
  useEffect(() => {
    const node = dialogRef.current
    if (!node || !open || !primary) return

    const focusables = () =>
      Array.from(node.querySelectorAll<HTMLButtonElement>('button')).filter((b) => !b.disabled)

    focusables()
      .find((b) => b.dataset.testid === 'approval-deny')
      ?.focus()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onDeny()
        return
      }
      if (e.key !== 'Tab') return
      const list = focusables()
      const first = list[0]
      const last = list[list.length - 1]
      if (!first || !last) return
      const active = document.activeElement

      if (e.shiftKey) {
        if (active === first || !node.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else if (active === last || !node.contains(active)) {
        e.preventDefault()
        first.focus()
      }
    }

    node.addEventListener('keydown', handleKeyDown)
    return () => node.removeEventListener('keydown', handleKeyDown)
  }, [onDeny, open, primary])

  return (
    <div
      ref={dialogRef}
      role={open && primary ? 'alertdialog' : 'group'}
      aria-label={open ? t('chat.approvalNeeded') : t('chat.toolApproval.headClosed')}
      data-testid="approval-card"
      data-gate-state={tool.approval?.state ?? tool.status}
      className={`glass-reading mb-2 rounded-lg border p-3 ${
        open ? 'border-status-warning/30 bg-status-warning/5' : 'border-control bg-surface/40'
      }`}
    >
      <div className="flex items-center gap-2">
        <ShieldAlert
          className={`h-4 w-4 shrink-0 ${open ? 'text-status-warning' : 'text-ink-faint'}`}
        />
        <span className="text-ui-sm text-foreground/80">
          {open ? t('chat.approvalNeeded') : t('chat.toolApproval.headClosed')}
        </span>
        <code className="rounded bg-canvas px-1.5 py-0.5 font-mono text-ui-xs text-status-warning">
          {tool.name}
        </code>
      </div>
      {(outcome || submitting) && (
        // The card says in one line what happened to this gate and by whose hand, so
        // an answered gate is never mistaken for one still waiting.
        <p
          role="status"
          aria-live="polite"
          data-testid={outcome ? 'approval-outcome' : 'approval-sending'}
          className={`mt-1 pl-6 text-ui-2xs ${
            tool.approval?.state === 'expired' ? 'text-status-warning/90' : 'text-ink-soft'
          }`}
        >
          {outcome ?? t('chat.toolApproval.sending')}
        </p>
      )}
      {tool.approval_diff ? (
        // Wave B1: a real unified-diff preview instead of raw JSON. No filePath →
        // DiffView is pure colour display (no apply/discard, nothing is on disk).
        <div data-testid="approval-diff" className="mt-1.5 pl-6">
          <DiffView diff={tool.approval_diff} />
        </div>
      ) : (
        <div className="mt-1 truncate pl-6 font-mono text-ui-xs text-ink-soft">{argsPreview}</div>
      )}
      {blast && (
        <div
          data-testid="approval-blast-radius"
          className="mt-1 truncate pl-6 text-ui-sm text-status-warning/80"
          title={blast}
        >
          <span className="text-ink-faint">{t('chat.toolApproval.blastRadius')}</span> {blast}
        </div>
      )}
      {(open || submitting) && (
        <>
          <div className="mt-2 flex flex-wrap gap-2 pl-6">
            {/* WP2b keep: approve (green) against deny (danger) is a semantic pair, not an accent.
            E2: the remembered approval is a second, named action rather than a checkbox the
            primary button silently carries — the reader sees what each click buys. */}
            <button
              type="button"
              onClick={() => onApprove(false)}
              disabled={!open}
              aria-label={t('chat.toolApproval.once')}
              data-testid="approval-once"
              className="flex items-center gap-1.5 rounded-md border border-status-success/30 bg-status-success/20 px-3 py-1.5 text-ui-xs text-status-success hover:bg-status-success/30 transition-colors disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" />
              {t('chat.toolApproval.once')}
            </button>
            {rememberable && (
              <button
                type="button"
                onClick={() => onApprove(true)}
                disabled={!open}
                aria-label={t('chat.toolApproval.remember')}
                data-testid="approval-remember"
                title={t('chat.toolApproval.remember')}
                className="flex items-center gap-1.5 rounded-md border border-control px-3 py-1.5 text-ui-xs text-ink-soft hover:bg-surface-interactive transition-colors disabled:opacity-40"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                {t('chat.toolApproval.remember')}
              </button>
            )}
            <button
              type="button"
              onClick={onDeny}
              disabled={!open}
              aria-label={t('chat.toolApproval.deny')}
              data-testid="approval-deny"
              className="flex items-center gap-1.5 rounded-md border border-status-danger/20 bg-status-danger/10 px-3 py-1.5 text-ui-xs text-status-danger hover:bg-status-danger/20 transition-colors disabled:opacity-40"
            >
              <X className="h-3.5 w-3.5" />
              {t('chat.toolApproval.deny')}
            </button>
            {onDenyWithCorrection && (
              <button
                type="button"
                onClick={() => setAsking((v) => !v)}
                disabled={!open}
                aria-expanded={asking}
                data-testid="approval-deny-with-correction"
                className="text-ui-xs text-ink-soft underline-offset-2 hover:underline disabled:opacity-40"
              >
                {t('chat.toolApproval.denyCorrect')}
              </button>
            )}
          </div>
          {asking && onDenyWithCorrection && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <input
                value={correction}
                onChange={(event) => setCorrection(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    submitCorrection()
                  }
                }}
                placeholder={t('chat.toolApproval.correction')}
                aria-label={t('chat.toolApproval.correction')}
                data-testid="approval-correction"
                className="flex-1 rounded-md border border-control bg-canvas px-2 py-1 text-ui-xs text-foreground/90 focus-ring"
              />
              <button
                type="button"
                onClick={submitCorrection}
                disabled={!correction.trim()}
                data-testid="approval-correction-send"
                className="rounded-md bg-status-danger/15 px-2 py-1 text-ui-xs text-status-danger disabled:opacity-40"
              >
                {t('chat.toolApproval.correctionSend')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
