import { ApiError } from '@/lib/api/http'
import type { ApprovalGate, ToolCall } from '@/types'
// The leaf of the store that declares its actions. Importing `@/store/chatStore`
// here would close the graph the architecture check forbids: the store's own action
// module calls into this one.
import type { ChatState } from '@/store/chat/types'

/**
 * The browser's copy of the server's approval window. `APPROVAL_TTL_SECONDS` in
 * `server/routes/chat.py` is the fact; this is the reader that must not run a card
 * past it. The server stays authoritative: a click that arrives after its own window
 * is answered 410 and closes the card as an expiry whatever the clock here said.
 */
export const SANDBOX_APPROVAL_WINDOW_MS = 300_000

/** The states a gate passes through. `submitting` is the request in flight — the
 *  card has no buttons left to press while it runs, so one token spends one POST. */
export type GateState = ApprovalGate['state']

/** Every gate record carries a token; a transcript written before `approval` existed
 *  kept the same token in `description`. Both match, so an old card still closes. */
export function gateToken(call: ToolCall): string {
  return call.approval?.token ?? call.description ?? ''
}

/** A gate that has been closed: answered by a hand, closed by the server, or run out.
 *  A closed gate has no buttons, and no click on it may put a request on the wire. */
export function gateIsClosed(call: ToolCall): boolean {
  if (call.status === 'expired') return true
  const state = call.approval?.state
  return state === 'answered' || state === 'expired'
}

/** The word a tool row carries for a gated call, or null when the call has no gate
 *  and the plain status rules of `toolOutcome` decide. A gate whose window ran out
 *  while the card sat open is an expiry, not a wait that is still running. */
export function gateRowWord(
  call: ToolCall,
  t: (key: string) => string,
  now = Date.now(),
): string | null {
  const gate = call.approval
  if (!gate) return null
  if (gate.state === 'waiting') {
    return now - gate.openedAt >= SANDBOX_APPROVAL_WINDOW_MS
      ? t('chat.toolApproval.rowExpired')
      : t('chat.toolWaiting')
  }
  if (gate.state === 'submitting') return t('chat.toolApproval.sending')
  if (gate.state === 'expired') return t('chat.toolApproval.rowExpired')
  if (gate.closedBy === 'server') return t('chat.toolApproval.rowSpent')
  return null
}

/** Still open for a decision: waiting, its window not run out, and no request away. */
export function gateIsAnswerable(call: ToolCall, now = Date.now()): boolean {
  const gate = call.approval
  if (!gate) return call.status === 'waiting'
  if (gate.state !== 'waiting') return false
  return now - gate.openedAt < SANDBOX_APPROVAL_WINDOW_MS
}

/** Gates past their window while the card sat open — the tick writes these, so an
 *  unanswered gate closes as an expiry. */
export function gatesPastWindow(calls: ToolCall[], now = Date.now()): string[] {
  return calls
    .filter(
      (c) =>
        c.approval?.state === 'waiting' && now - c.approval.openedAt >= SANDBOX_APPROVAL_WINDOW_MS,
    )
    .map(gateToken)
    .filter(Boolean)
}

/** The slice of the store the decision path drives; the real store satisfies it. */
export type SandboxGateStore = Pick<
  ChatState,
  | 'sandboxGateOpen'
  | 'markSandboxSubmitting'
  | 'approveSandbox'
  | 'denySandbox'
  | 'markSandboxExpired'
  | 'closeSandboxSpent'
  | 'reopenSandbox'
>

/**
 * One gate, one request.
 *
 * The store is read synchronously and the gate moves to `submitting` in the same tick
 * as the click, so no second request for a token can leave the browser — finding 40
 * measured 466 clicks on one token the server had already spent, 463 of them answered
 * 404 by a card that still looked open.
 *
 * Each shape of failure closes the gate as the server describes it: an expired window
 * is an expiry, a spent token is spent, and neither is written as a decision of the
 * reader. Only a request that never reached the server opens the gate again.
 */
export async function sendSandboxDecision(
  store: SandboxGateStore,
  token: string,
  approved: boolean,
  by: 'you' | 'companion',
  send: (token: string, approved: boolean) => Promise<unknown>,
  onUnavailable: () => void,
): Promise<void> {
  if (!store.sandboxGateOpen(token)) return
  store.markSandboxSubmitting(token)
  try {
    await send(token, approved)
    if (approved) store.approveSandbox(token, by)
    else store.denySandbox(token, by)
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0
    if (status === 410) store.markSandboxExpired(token)
    else if (status === 404) store.closeSandboxSpent(token)
    else {
      store.reopenSandbox(token)
      onUnavailable()
    }
  }
}
