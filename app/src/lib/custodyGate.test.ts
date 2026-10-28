import { describe, expect, it } from 'vitest'
import { evaluateCustodyGate } from './custodyGate'

describe('evaluateCustodyGate (J2)', () => {
  it('refuses the author signing its own change set', () => {
    expect(evaluateCustodyGate('agent-a', 'agent-a')).toBe('SELF_SIGN_FORBIDDEN')
  })

  it('trims the signer the way the form submits it', () => {
    expect(evaluateCustodyGate('agent-a', '  agent-a ')).toBe('SELF_SIGN_FORBIDDEN')
    expect(evaluateCustodyGate('agent-a', 'agent-b')).toBe('ok')
  })

  it('does not fold case, because the backend does not either', () => {
    expect(evaluateCustodyGate('Agent-A', 'agent-a')).toBe('ok')
  })

  it('cannot judge an empty author or signer', () => {
    expect(evaluateCustodyGate('', '')).toBe('ok')
    expect(evaluateCustodyGate('agent-a', '')).toBe('ok')
  })
})
