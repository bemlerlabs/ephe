/**
 * #57 — the Plan-Accept pair and the mode vocabulary, held together by a test.
 *
 * The locale leaf `chat.planAcceptMsg` is the sentence the Accept click sends to the engine
 * (`PlanCard.tsx`), and the walkthrough `e2e/walkthrough/plan-accept.spec.ts` asserts against
 * it. Both used names that the Wave 0/1 rename retired ("Plan mode", "write tools"), so the
 * copy and the walkthrough described a product that no longer existed. Renaming one without
 * the other is how the pair drifted; this file fails on the drift instead of on a 15-minute
 * live run:
 *
 * - the sentence must name the mode it leaves — the head of `chat.modeHint.architect` — and
 *   the state it enters — `chat.modeSection.write`, which is what the chip draws for the
 *   untiled `edit-auto` (`ComposerModeChip.tsx`);
 * - no retired mode name may appear in it, in either language;
 * - the walkthrough must click tile keys that exist, and the fragment it looks for on the
 *   wire must be in the English sentence.
 *
 * The tiled vocabulary is read from `chat.modeHint`: one translated hint per tile the menu
 * offers, so a tile added or renamed without this file notices.
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from '../locales/en.json'
import de from '../locales/de.json'
import { DEFAULT_COMPOSER_MODE } from '../store/chat/helpers'
import { PLAN_EXECUTION_MODE } from './planCardModel'

/** app/, found from the run's cwd (vitest runs at the app or the repo root). */
function appFile(rel: string): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, rel)
    if (existsSync(candidate)) return candidate
  }
  throw new Error(`${rel} not found below the app root`)
}

/** The short chip label: the head of the hint before the em dash (`modeShortLabel`). */
function shortLabel(hint: string): string {
  return hint.split('—')[0]?.trim() ?? hint
}

const catalogs = { en, de } as const
const tiledModes = Object.keys(en.chat.modeHint)
const spec = readFileSync(appFile('e2e/walkthrough/plan-accept.spec.ts'), 'utf8')

describe('the Plan-Accept pair speaks the current mode vocabulary', () => {
  it('has one translated hint per menu tile, and no tile for the compatibility value', () => {
    expect(tiledModes).toEqual(['analyst', 'architect', 'operator', 'creator'])
    expect(tiledModes).not.toContain(PLAN_EXECUTION_MODE)
    expect(PLAN_EXECUTION_MODE).toBe('edit-auto')
  })

  it.each(['en', 'de'] as const)('names Architect and write access (%s)', (lang) => {
    const chat = catalogs[lang].chat
    const message = chat.planAcceptMsg
    const architect = shortLabel(chat.modeHint.architect)
    expect(message).toContain(architect)
    // The section wording is a chip label ("With write access"); inside the sentence it is
    // lowercase, so compare the words, not the capitalisation the chip gives them.
    expect(message.toLowerCase()).toContain(chat.modeSection.write.toLowerCase())
    // What the mode may now run, and what still asks. The pair's claim.
    expect(message).toContain('write_file')
    expect(message).toContain('edit_file')
  })

  it.each(['en', 'de'] as const)('carries no retired mode name (%s)', (lang) => {
    const message = catalogs[lang].chat.planAcceptMsg
    for (const retired of [
      /plan[- ]?mode/i,
      /plan-modus/i,
      /write tools/i,
      /schreib-werkzeuge/i,
      /\bedit[ -]?auto\b/i,
      /\bfull[ -]?access\b/i,
      /\bask mode\b/i,
    ]) {
      expect(message, `retired vocabulary in ${lang}: ${retired}`).not.toMatch(retired)
    }
  })

  it('chains the walkthrough to the same words instead of a private copy', () => {
    // The lead the spec looks for on the captured POST — `message.includes('left Architect')`.
    const fragment = /message\.includes\('([^']+)'\)/.exec(spec)?.[1]
    expect(fragment).toBeTruthy()
    expect(en.chat.planAcceptMsg).toContain(fragment!)

    // The chip the spec expects after Accept: the section wording, lowercased.
    const executionChip = /const EXECUTION_CHIP = '([^']+)'/.exec(spec)?.[1]
    expect(executionChip).toBe(en.chat.modeSection.write.toLowerCase())

    // The planning tile it clicks: the hint's short label, lowercased.
    const planChip = /const PLAN_CHIP = '([^']+)'/.exec(spec)?.[1]
    expect(planChip).toBe(shortLabel(en.chat.modeHint.architect).toLowerCase())

    // Every mode the spec picks must be a tile; the restore target is the product default.
    const picked = [
      ...spec.matchAll(/pickMode\(page, (?:shot|async \(\) => \{\}), '([a-z-]+)'\)/g),
    ].map((match) => match[1])
    expect(picked.length).toBeGreaterThan(0)
    for (const mode of picked) expect(tiledModes).toContain(mode)
    const defaultMode = /const DEFAULT_MODE = '([^']+)'/.exec(spec)?.[1]
    expect(defaultMode).toBe(DEFAULT_COMPOSER_MODE)
  })

  it('leaves no retired composer-mode key in the walkthrough docs', () => {
    for (const rel of [
      'e2e/walkthrough/plan-accept.spec.ts',
      'e2e/walkthrough/modes-matrix.spec.ts',
      'e2e/walkthrough/what-it-tells-you.spec.ts',
    ]) {
      const text = readFileSync(appFile(rel), 'utf8')
      for (const retired of ['ask', 'plan', 'edit-auto', 'full-access']) {
        expect(text, `${rel} still queries composer-mode-${retired}`).not.toContain(
          `composer-mode-${retired}`,
        )
      }
    }
  })
})
