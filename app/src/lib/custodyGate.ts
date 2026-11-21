/**
 * QD-013 (J2): who may sign a change set.
 *
 * The rule is the backend's, not a second opinion: `core/review_gate.py` compares
 * the reviewer it receives with the author and answers `self_sign_forbidden` when
 * they are the same string. The form trims before it submits, so this mirrors the
 * comparison on the wire — no case folding, because the gate does none either.
 */
export type CustodyGateVerdict = 'ok' | 'SELF_SIGN_FORBIDDEN'

export function evaluateCustodyGate(author: string, signer: string): CustodyGateVerdict {
  const owner = String(author ?? '')
  const who = String(signer ?? '').trim()
  return owner !== '' && who === owner ? 'SELF_SIGN_FORBIDDEN' : 'ok'
}
