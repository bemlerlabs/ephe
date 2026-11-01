/**
 * W1 — the small words of the workspaces surface, tested where they are decided.
 *
 * The two rules worth pinning: an unknown state must print as itself rather than as a key
 * path, and an age must survive the register's own stamp format (six fractional digits and
 * a `+00:00` offset), because a stamp one engine parses and another does not is how "3h"
 * becomes "NaN" on exactly one browser.
 */
import { describe, it, expect } from 'vitest'
import {
  ageLabel,
  ageOf,
  ageOfSeconds,
  changeSetStateTone,
  diffPrefix,
  opTone,
  refusalSentence,
  vocabLabel,
  workspaceStateTone,
} from './labels'
import { ApiError } from '@/lib/api'

const t = (key: string) => key

describe('ageOf', () => {
  const now = Date.parse('2026-10-14T12:00:00.000Z')

  it('reads the register stamp with microseconds and an offset', () => {
    // The register writes six fractional digits and `+00:00`; an unparseable stamp would
    // answer null, so this is the assertion that the stamp is read at all.
    expect(ageOf('2026-10-14T11:45:00.123456+00:00', now)).toEqual({ unit: 'minutes', n: 14 })
    // …and the fraction is honoured rather than dropped: the same stamp without it is a
    // full minute older, which is the difference the two readings must show.
    expect(ageOf('2026-10-14T11:45:00+00:00', now)).toEqual({ unit: 'minutes', n: 15 })
  })

  it('steps through the three units', () => {
    expect(ageOf('2026-10-14T11:59:30+00:00', now)).toEqual({ unit: 'now', n: 0 })
    expect(ageOf('2026-10-14T07:00:00+00:00', now)).toEqual({ unit: 'hours', n: 5 })
    expect(ageOf('2026-10-11T12:00:00+00:00', now)).toEqual({ unit: 'days', n: 3 })
  })

  it('answers nothing rather than a wrong number', () => {
    expect(ageOf('', now)).toBeNull()
    expect(ageOf('not a date', now)).toBeNull()
  })

  it('never counts backwards when the clock is ahead of the stamp', () => {
    expect(ageOf('2026-10-14T12:00:30+00:00', now)).toEqual({ unit: 'now', n: 0 })
  })
})

describe('diffPrefix', () => {
  it('keeps the algorithm and the head of the digest', () => {
    expect(diffPrefix(`sha256:${'a1b2c3d4'.repeat(8)}`)).toBe('sha256:a1b2c3d4')
  })

  it('leaves a digest that is already short alone', () => {
    expect(diffPrefix('sha256:abc')).toBe('sha256:abc')
  })

  it('does not invent an algorithm that was never there', () => {
    expect(diffPrefix('deadbeefdeadbeef')).toBe('deadbeef')
    expect(diffPrefix('')).toBe('')
  })

  it('answers a file the server never hashed with nothing, not a crash', () => {
    // D0-4: /workspaces fell over on a change set whose files carried no diff_sha,
    // because the projection read the field as if every answer had it.
    expect(diffPrefix(undefined)).toBe('')
  })
})

describe('vocabLabel', () => {
  it('names the words the domain actually uses', () => {
    expect(vocabLabel('state', 'dirty', t)).toBe('workspaces.state.dirty')
    expect(vocabLabel('op', 'delete', t)).toBe('workspaces.op.delete')
    expect(vocabLabel('changeSetState', 'review', t)).toBe('workspaces.changeSetState.review')
    expect(vocabLabel('verdict', 'request_changes', t)).toBe('workspaces.verdict.request_changes')
  })

  it('prints an unknown state as itself instead of as a key path', () => {
    expect(vocabLabel('state', 'quarantined', t)).toBe('quarantined')
    expect(vocabLabel('op', 'rename', t)).toBe('rename')
    expect(vocabLabel('verdict', 'maybe', t)).toBe('maybe')
  })
})

describe('tones', () => {
  it('carries each state on a badge variant that exists', () => {
    expect(workspaceStateTone('dirty')).toBe('warning')
    expect(workspaceStateTone('ready')).toBe('success')
    expect(changeSetStateTone('rejected')).toBe('destructive')
    expect(opTone('delete')).toBe('destructive')
  })

  it('gives an unknown state the quiet variant, not a colour that means something', () => {
    expect(workspaceStateTone('quarantined')).toBe('outline')
    expect(changeSetStateTone('quarantined')).toBe('outline')
  })
})

describe('refusalSentence', () => {
  it('carries a plain error as it was written', () => {
    expect(refusalSentence(new Error('the backend did not answer in time'))).toBe(
      'the backend did not answer in time',
    )
  })

  it('turns a thrown mapping into a sentence instead of a placeholder', () => {
    expect(refusalSentence({ detail: 'the register has no tree w9' })).toBe(
      'the register has no tree w9',
    )
    expect(refusalSentence({ reason: 'aborted before publish: the tree moved' })).toBe(
      'aborted before publish: the tree moved',
    )
  })

  it('answers nothing at all rather than [object Object] when nothing is readable', () => {
    expect(refusalSentence({ status: 409 })).toBe('')
    expect(refusalSentence(undefined)).toBe('')
    expect(refusalSentence(null)).toBe('')
  })
})

describe('refusalSentence and a code whose slots cannot be filled', () => {
  it('prefers the server sentence over a bundle entry still carrying {{slots}}', () => {
    // `review_refused` renders `{{reason}}`, and the params ride in a field `ApiError` does
    // not keep — so the template used to reach the reader with the placeholder in it.
    const refused = new ApiError(
      'demo-worker authored cs-1 and cannot approve it',
      422,
      'review_refused',
    )

    expect(refusalSentence(refused)).toBe('demo-worker authored cs-1 and cannot approve it')
    expect(refusalSentence(refused)).not.toContain('{{')
  })

  it('still lets a code with no slots in it win', () => {
    const refused = new ApiError('the tree moved after this set was recorded: values.py', 409, '')

    expect(refusalSentence(refused)).toBe('the tree moved after this set was recorded: values.py')
  })
})

describe('ageOfSeconds', () => {
  it('steps through the same units as the stamp reading', () => {
    expect(ageOfSeconds(45)).toEqual({ unit: 'now', n: 0 })
    expect(ageOfSeconds(90)).toEqual({ unit: 'minutes', n: 1 })
    expect(ageOfSeconds(2 * 3600 + 5)).toEqual({ unit: 'hours', n: 2 })
    expect(ageOfSeconds(50 * 3600)).toEqual({ unit: 'days', n: 2 })
  })

  it('answers nothing for a count that is not a measured age', () => {
    // The fleet sends null when it saw no event; a row without one falls back to the birth.
    expect(ageOfSeconds(null)).toBeNull()
    expect(ageOfSeconds(undefined)).toBeNull()
    expect(ageOfSeconds(-5)).toBeNull()
    expect(ageOfSeconds(Number.NaN)).toBeNull()
  })
})

describe('ageLabel', () => {
  const now = Date.parse('2026-10-14T12:00:00.000Z')
  const key = (k: string, options?: Record<string, unknown>) =>
    options ? `${k} ${JSON.stringify(options)}` : k

  it('says the same thing AgeText renders, as one string a slot can carry', () => {
    // The holder line is assembled inside a translation value, where a component cannot go.
    expect(ageLabel('2026-10-14T11:45:00.123456+00:00', key, now)).toBe(
      'workspaces.age.minutes {"n":14}',
    )
    expect(ageLabel('2026-10-14T11:59:30+00:00', key, now)).toBe('workspaces.ageNow')
    expect(ageLabel('2026-10-11T12:00:00+00:00', key, now)).toBe('workspaces.age.days {"n":3}')
  })

  it('answers an empty string rather than a placeholder for a stamp it cannot read', () => {
    expect(ageLabel('', key, now)).toBe('')
    expect(ageLabel('not a date', key, now)).toBe('')
  })
})
