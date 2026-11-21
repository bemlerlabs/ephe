/**
 * The refusal reader. A coded server answer is resolved through the bundle so
 * the reader gets their own language; an unknown code or a bundle without the
 * entry returns the caller's fallback (the server's own sentence) — a missing
 * translation costs a language, never the message.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { exists, t } = vi.hoisted(() => ({ exists: vi.fn(), t: vi.fn() }))
vi.mock('@/i18n', () => ({ default: { exists, t } }))

import { serverErrorText } from './serverError'

describe('serverErrorText', () => {
  beforeEach(() => {
    exists.mockReset()
    t.mockReset()
  })

  it('returns the fallback when the code is missing', () => {
    expect(serverErrorText(undefined, undefined, 'raw server sentence')).toBe('raw server sentence')
    expect(exists).not.toHaveBeenCalled()
  })

  it('returns an empty string when neither code nor fallback is given', () => {
    expect(serverErrorText(undefined)).toBe('')
  })

  it('returns the fallback when the bundle has no entry for the code', () => {
    exists.mockReturnValue(false)
    expect(serverErrorText('unknown_code', undefined, 'fallback text')).toBe('fallback text')
  })

  it('resolves a known code through the bundle', () => {
    exists.mockReturnValue(true)
    t.mockReturnValue('The server refused the request.')
    expect(serverErrorText('image_refused')).toBe('The server refused the request.')
    expect(exists).toHaveBeenCalledWith('serverError.image_refused')
    expect(t).toHaveBeenCalledWith('serverError.image_refused', { defaultValue: '' })
  })

  it('forwards params and the fallback as defaultValue', () => {
    exists.mockReturnValue(true)
    t.mockReturnValue('ok')
    serverErrorText('rate_limited', { seconds: 30 }, 'slow down')
    expect(t).toHaveBeenCalledWith('serverError.rate_limited', {
      seconds: 30,
      defaultValue: 'slow down',
    })
  })

  it('coerces a non-string translation to a string', () => {
    exists.mockReturnValue(true)
    t.mockReturnValue(42)
    expect(serverErrorText('x')).toBe('42')
  })
})
