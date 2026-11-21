import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import ToolApprovalPrompt from '../ToolApprovalPrompt'
import { gateIsAnswerable, gatesPastWindow } from '@/lib/sandboxGate'
import { useChatStore, type ToolCall } from '@/store/chatStore'

/** Tick of the expiry watch. A gate that outlives its window closes itself as an
 *  expiry on this tick; the server's 410 stays authoritative for a click that beats
 *  it. Five seconds is coarse against a 300-second window and cheap while open. */
const TICK_MS = 5_000

/**
 * Every approval gate of one assistant turn, in transcript order.
 *
 * One card per gate (audit finding 40): the oldest gate answered cannot hide the
 * newest one waiting, because each renders from its own `approval` record and none of
 * them is looked up by position. More than one open gate says so with a count, and
 * only the first open one takes focus and announces — the rest are ordinary groups a
 * Tab reaches without stealing the focus of the question being asked.
 */
export default function ApprovalGates({
  calls,
  onApprove,
  onDeny,
  onDenyWithCorrection,
}: {
  calls?: ToolCall[]
  onApprove: (call: ToolCall, remember?: boolean) => void
  onDeny: (call: ToolCall) => void
  onDenyWithCorrection?: (call: ToolCall, text: string) => void
}) {
  const { t } = useTranslation()
  const gates = useMemo(() => (calls ?? []).filter((c) => c.approval), [calls])
  const openCount = gates.filter((c) => gateIsAnswerable(c)).length
  const primaryToken = gates.find((c) => gateIsAnswerable(c))?.approval?.token
  const latest = useRef(gates)
  latest.current = gates

  useEffect(() => {
    if (!gates.some((c) => gateIsAnswerable(c))) return
    const id = window.setInterval(() => {
      for (const token of gatesPastWindow(latest.current)) {
        useChatStore.getState().markSandboxExpired(token)
      }
    }, TICK_MS)
    return () => window.clearInterval(id)
  }, [gates])

  if (gates.length === 0) return null

  return (
    <div data-testid="approval-gates">
      {openCount > 1 && (
        <p
          role="status"
          aria-live="polite"
          data-testid="approval-open-count"
          className="mb-1 text-ui-2xs text-ink-soft"
        >
          {t('chat.toolApproval.multipleWaiting', { count: openCount })}
        </p>
      )}
      {gates.map((call) => (
        <ToolApprovalPrompt
          key={call.approval?.token ?? call.id}
          tool={call}
          rememberable={call.rememberable}
          primary={call.approval?.token === primaryToken}
          onApprove={(remember?: boolean) => onApprove(call, remember)}
          onDeny={() => onDeny(call)}
          onDenyWithCorrection={
            onDenyWithCorrection ? (text: string) => onDenyWithCorrection(call, text) : undefined
          }
        />
      ))}
    </div>
  )
}
