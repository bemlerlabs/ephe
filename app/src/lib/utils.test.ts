/**
 * Wave #55: the clock follows the interface language, not the language that
 * happened to stand in the code. `formatTime` was pinned to `de-DE`, so an
 * English interface printed German time conventions on every chat bubble.
 *
 * The expectations are literals per language on purpose. An expectation built
 * with the same formatter it checks (the old `(8192 - 4135).toLocaleString()`
 * shape) follows the machine and can therefore never fail.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { cn, formatTime } from './utils'

const afternoon = new Date(2026, 9, 9, 14, 35)
const morning = new Date(2026, 9, 9, 9, 5)

describe('formatTime — the surface language decides the clock', () => {
  it('german reads 24 hours with the leading zero, unchanged from before', () => {
    expect(formatTime(afternoon, 'de')).toBe('14:35')
    expect(formatTime(morning, 'de')).toBe('09:05')
  })

  it('english reads 12 hours with AM/PM', () => {
    expect(formatTime(afternoon, 'en')).toBe('2:35 PM')
    expect(formatTime(morning, 'en')).toBe('9:05 AM')
  })

  it('a string date and a Date arrive at the same reading', () => {
    expect(formatTime('2026-10-09T14:35:00', 'de')).toBe(formatTime(afternoon, 'de'))
  })

  it('with no stored choice the interface is English, so the clock is too', () => {
    expect(formatTime(afternoon)).toBe('2:35 PM')
  })
})

/** The size steps and the ink names meet in `cn`, and for a long while they met
 *  wrongly there: tailwind-merge read `text-ui-xs` as a text colour, so a size
 *  and an ink in one merged string came back as the ink alone — nothing thrown,
 *  nothing logged, and 838 lines over 137 files carry both. The classification
 *  is held against the sheet itself rather than against a list of names, so the
 *  eleventh step and the step after it are covered by the same two assertions. */
const sheet = readFileSync('src/styles/globals.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')

/** Every `--text-*` key of the sheet with the value beside it. A length — a
 *  `calc()`, a pixel figure, or a pointer at a scalar variable such as the
 *  `--ui-font-size` lever — is a size step; a pointer at a `--color-*` role is
 *  an ink; and the `--line-height` halves belong to a step and never stand on
 *  their own. The class a key becomes is the key without its leading `--`. */
const textTokens = [...sheet.matchAll(/(--text-[a-z0-9-]+)\s*:\s*([^;]+);/g)].flatMap((m) =>
  m[1] && m[2] ? [{ name: m[1], value: m[2].trim() }] : [],
)
const isInk = (t: { value: string }) => t.value.startsWith('var(--color-')
const isStep = (t: { value: string }) =>
  !isInk(t) && /^calc\(|^var\(--|^\d+(?:\.\d+)?(?:px|rem|em)$/.test(t.value)
const steps = textTokens.filter(isStep)
const inks = textTokens.filter(isInk)
const asClass = (name: string) => name.replace(/^--/, '')

describe('cn — a type step survives the ink beside it', () => {
  it('keeps the size when a colour is merged behind it', () => {
    expect(cn('text-ui-xs', 'text-ink-faint')).toBe('text-ui-xs text-ink-faint')
    expect(cn('text-scale-data', 'text-brand-deep')).toBe('text-scale-data text-brand-deep')
    expect(cn('text-base', 'text-ink-soft')).toBe('text-base text-ink-soft')
  })

  it('still lets a colour beat a colour and a size beat a size', () => {
    expect(cn('text-ink-faint', 'text-ink')).toBe('text-ink')
    expect(cn('text-role-primary', 'text-ink-faint')).toBe('text-ink-faint')
    expect(cn('text-ui-xs', 'text-ui-sm')).toBe('text-ui-sm')
    expect(cn('text-scale-ui', 'text-scale-title')).toBe('text-scale-title')
  })

  it('reads every size step of the sheet as a size, ink and all', () => {
    // A floor that guards a parse gone blind: a wave adding a step does not
    // have to touch this number.
    expect(steps.length).toBeGreaterThanOrEqual(11)
    expect(inks.length).toBeGreaterThanOrEqual(3)
    for (const step of steps) {
      const cls = asClass(step.name)
      expect(`${step.name} → ${cn(cls, 'text-ink-faint')}`).toBe(
        `${step.name} → ${cls} text-ink-faint`,
      )
    }
    for (const ink of inks) {
      expect(`${ink.name} → ${cn(asClass(ink.name), 'text-ink-faint')}`).toBe(
        `${ink.name} → text-ink-faint`,
      )
    }
  })

  it('names every --text-* key of the sheet as a step, an ink, or neither', () => {
    // An unread value shape lands here, where the author of the next step sees
    // that the merge has not been told about it yet.
    const unread = textTokens.filter((t) => !steps.includes(t) && !inks.includes(t))
    expect(unread.map((t) => `${t.name}: ${t.value}`)).toEqual([])
  })
})
