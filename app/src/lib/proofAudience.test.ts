import { describe, expect, it } from 'vitest'
import { audienceOf, proofText } from './proofAudience'

describe('proof audience', () => {
  it('reads the disclosure mode as the audience', () => {
    expect(audienceOf('collapsed')).toBe('everyday')
    expect(audienceOf('expanded')).toBe('expert')
    expect(audienceOf(null)).toBe('everyday')
    expect(audienceOf('something-else')).toBe('everyday')
  })

  it('tells the everyday reader that it held, in seconds', () => {
    expect(proofText('everyday', { ok: true, ms: 412 })).toEqual({
      key: 'chat.proof.everyday',
      values: { seconds: '0.4' },
    })
  })

  it('tells the expert reader what it cost, in milliseconds', () => {
    expect(proofText('expert', { ok: true, ms: 412 })).toEqual({
      key: 'chat.proof.expert',
      values: { ms: 412 },
    })
  })

  it('invents no duration the stream never reported', () => {
    expect(proofText('everyday', { ok: true, ms: null }).key).toBe('chat.proof.everydayNoTime')
    expect(proofText('expert', { ok: true }).key).toBe('chat.proof.expertNoTime')
  })

  it('names a failure for both readers', () => {
    expect(proofText('everyday', { ok: false, ms: 900 }).key).toBe('chat.proof.failed')
    expect(proofText('expert', { ok: false }).key).toBe('chat.proof.failed')
  })
})
