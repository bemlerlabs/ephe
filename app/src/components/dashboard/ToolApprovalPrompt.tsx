import { useEffect, useRef } from 'react'
import { ShieldAlert, Check, ShieldCheck, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import DiffView from './DiffView'
import type { ToolCall } from '@/store/chatStore'

/**
 * Inline tool-approval banner (PWA-Chat-UX-Plan, task B5).
 * Appears when the backend sends a sandbox_confirm event
 * (tool call in status 'waiting', description = sandbox token).
 *
 * D1 a11y:
 * - role="alertdialog" + aria-label (screen-reader announcement)
 * - initial focus on Deny (conservative: approving needs an
 *   explicit Tab/click — no accidental approve)
 * - focus trap: Tab/Shift+Tab cycle inside the action row, whatever it holds
 * - Esc = escape hatch → onDeny
 *
 * Architecture: renders UI only and calls onApprove/onDeny — the API call
 * (POST /api/sandbox/approve) belongs in the wiring (task C1).
 */
export default function ToolApprovalPrompt({
  tool,
  rememberable = false,
  onApprove,
  onDeny,
}: {
  tool: ToolCall
  rememberable?: boolean
  onApprove: (remember?: boolean) => void
  onDeny: () => void
}) {
  const { t } = useTranslation()
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

  // Initial focus on Deny (conservative) + Tab focus trap + Esc
  useEffect(() => {
    const node = dialogRef.current
    if (!node) return

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
  }, [onDeny])

  return (
    <div
      ref={dialogRef}
      role="alertdialog"
      aria-label={t('chat.approvalNeeded')}
      className="glass-reading mb-2 rounded-lg border border-status-warning/30 bg-status-warning/5 p-3"
    >
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 shrink-0 text-status-warning" />
        <span className="text-ui-sm text-foreground/80">{t('chat.approvalNeeded')}</span>
        <code className="rounded bg-canvas px-1.5 py-0.5 font-mono text-ui-xs text-status-warning">
          {tool.name}
        </code>
      </div>
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
      <div className="mt-2 flex flex-wrap gap-2 pl-6">
        {/* WP2b keep: approve (green) against deny (danger) is a semantic pair, not an accent.
            E2: the remembered approval is a second, named action rather than a checkbox the
            primary button silently carries — the reader sees what each click buys. */}
        <button
          type="button"
          onClick={() => onApprove(false)}
          aria-label={t('chat.toolApproval.once')}
          data-testid="approval-once"
          className="flex items-center gap-1.5 rounded-md border border-status-success/30 bg-status-success/20 px-3 py-1.5 text-ui-xs text-status-success hover:bg-status-success/30 transition-colors"
        >
          <Check className="h-3.5 w-3.5" />
          {t('chat.toolApproval.once')}
        </button>
        {rememberable && (
          <button
            type="button"
            onClick={() => onApprove(true)}
            aria-label={t('chat.toolApproval.remember')}
            data-testid="approval-remember"
            title={t('chat.toolApproval.remember')}
            className="flex items-center gap-1.5 rounded-md border border-control px-3 py-1.5 text-ui-xs text-ink-soft hover:bg-surface-interactive transition-colors"
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            {t('chat.toolApproval.remember')}
          </button>
        )}
        <button
          type="button"
          onClick={onDeny}
          aria-label={t('chat.toolApproval.deny')}
          data-testid="approval-deny"
          className="flex items-center gap-1.5 rounded-md border border-status-danger/20 bg-status-danger/10 px-3 py-1.5 text-ui-xs text-status-danger hover:bg-status-danger/20 transition-colors"
        >
          <X className="h-3.5 w-3.5" />
          {t('chat.toolApproval.deny')}
        </button>
      </div>
    </div>
  )
}
