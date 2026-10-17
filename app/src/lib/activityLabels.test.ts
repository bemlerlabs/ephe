/**
 * Ephe — activityLabels: localise backend phase labels (G8)
 *
 * GIVEN  localizeActivityLabel with an EN phase string from core/chat.py
 * WHEN   known label → i18n key (chat.phase*)
 * THEN   translated label; groups (round/model/name) are passed through
 * AND    unknown label (tool command/artifact) → unchanged (passthrough)
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'
import i18next from 'i18next'
import { localizeActivityLabel } from './activityLabels'
import deLocale from '@/locales/de.json'
import enLocale from '@/locales/en.json'

type T = (key: string, opts?: Record<string, unknown>) => string

/**
 * The live phase string is parsed out of the producer instead of being retyped
 * here. This pair drifted once: `activityLabels.ts` kept matching the old German
 * `Name … existiert` wording while `core/skill_builder.py` had moved to
 * `name … exists`, so the rule never fired on real output — and the test stayed
 * green against a producer that no longer exists. Reading the source file makes
 * that state unrepresentable: change either side and this file fails.
 */
const here = dirname(fileURLToPath(import.meta.url))
const skillBuilderSrc = readFileSync(resolve(here, '../../../core/skill_builder.py'), 'utf8')

/** Sample slot values, so the parsed f-string becomes one concrete live string. */
const PHASE_SLOTS: Record<string, string> = {
  'parsed.name': 'pdf',
  unique_name: 'pdf-2',
}

/** Render the producer's `on_phase(f"…")` literal for the given emoji. */
function livePhase(emoji: string): string {
  const line = skillBuilderSrc.split('\n').find((l) => l.includes('on_phase(') && l.includes(emoji))
  const template = line?.match(/on_phase\(f?"([^"]*)"/)?.[1]
  if (!template) throw new Error(`core/skill_builder.py emits no on_phase() with ${emoji}`)
  return template.replace(/\{([^}]+)\}/g, (_slot, expr: string) => {
    const value = PHASE_SLOTS[expr.trim()]
    if (value === undefined) {
      throw new Error(
        `core/skill_builder.py now renders {${expr}} — teach PHASE_SLOTS what it holds`,
      )
    }
    return value
  })
}

/** Exactly what the backend puts on the wire today (core/skill_builder.py, 📝 phase). */
const NAME_EXISTS_PHASE = livePhase('📝')

/** Real bundles, so the gate is the render the user sees rather than a stub. */
function createInstance(lng: 'de' | 'en') {
  const inst = i18next.createInstance()
  // Resources are inline, so the store is filled during init and t() is
  // synchronous — the same detour i18n-keys.test.ts uses.
  void inst.init({
    resources: { de: { translation: deLocale }, en: { translation: enLocale } },
    lng,
    fallbackLng: lng,
    supportedLngs: [lng],
    interpolation: { escapeValue: false },
  })
  return inst
}

describe('localizeActivityLabel', () => {
  const de: T = (k, o) => {
    switch (k) {
      case 'chat.phaseAnalyzing':
        return 'Anfrage wird analysiert…'
      case 'chat.phaseLoadingModel':
        return 'Modell wird geladen… (Retry)'
      case 'chat.phaseFallbackModel':
        return `Hauptmodell: ${String(o?.model)}`
      case 'chat.phaseToolRound':
        return `Tool-Runde ${String(o?.round)}…`
      case 'chat.phaseProcessing':
        return 'Ergebnisse werden verarbeitet…'
      case 'chat.phaseGenerating':
        return 'Antwort wird erstellt…'
      case 'chat.phaseAnalyzingPatterns':
        return '📚 Code-Muster…'
      case 'chat.phaseSavingSkill':
        return '💾 Skill speichern…'
      case 'chat.phaseNameExists':
        return `Name ${String(o?.name)} → ${String(o?.unique)}`
      default:
        return k
    }
  }

  it('bekannte Phase-Strings werden übersetzt (de)', () => {
    expect(localizeActivityLabel('Analyzing request…', de)).toBe('Anfrage wird analysiert…')
    expect(localizeActivityLabel('Loading model… (Retry)', de)).toBe('Modell wird geladen… (Retry)')
    expect(localizeActivityLabel('Generating response…', de)).toBe('Antwort wird erstellt…')
    expect(localizeActivityLabel('Processing results…', de)).toBe('Ergebnisse werden verarbeitet…')
  })

  it('f-Strings mit Gruppen (round/model/name) werden durchgereicht', () => {
    expect(localizeActivityLabel('Tool round 2…', de)).toBe('Tool-Runde 2…')
    expect(
      localizeActivityLabel('Primary model needs more memory; retrying with qwen3:14b…', de),
    ).toBe('Hauptmodell: qwen3:14b')
    // Derived from the producer: asserts against the string that is really sent.
    expect(localizeActivityLabel(NAME_EXISTS_PHASE, de), NAME_EXISTS_PHASE).toBe('Name pdf → pdf-2')
  })

  it('unbekanntes Label (Tool-Command/Artifact) bleibt unverändert', () => {
    expect(localizeActivityLabel('search_web({"q":"ki"})', de)).toBe('search_web({"q":"ki"})')
    expect(localizeActivityLabel('Artifact: pdf', de)).toBe('Artifact: pdf')
    expect(localizeActivityLabel('git status → ok', de)).toBe('git status → ok')
    expect(localizeActivityLabel('📊 Chart created', de)).toBe('📊 Chart created')
    expect(localizeActivityLabel('', de)).toBe('')
  })

  it('alle on_phase()-Strings aus core/chat.py + skill_builder.py matchen', () => {
    // Strings from core/chat.py (on_phase calls) plus the derived 📝 phase from
    // core/skill_builder.py — the latter is read from the source file, not retyped.
    const backendStrings = [
      'Analyzing request…',
      'Loading model… (Retry)',
      'Primary model needs more memory; retrying with gemma4:7b…',
      'Tool round 1…',
      'Processing results…',
      'Generating response…',
      '📚 Analyzing code patterns…',
      '💾 Saving skill…',
      NAME_EXISTS_PHASE,
    ]
    const passthrough: T = (k) => `KEY:${k}`
    for (const s of backendStrings) {
      // The old shape mapped a miss onto `KEY:no-match`, which still contained
      // `KEY:` — the loop could never fail, so it never reported the drift it
      // existed to report. Assert the miss directly.
      const out = localizeActivityLabel(s, passthrough)
      expect(out, `String matcht NICHT: ${s}`).not.toBe(s)
      expect(out).toContain('KEY:')
    }
  })

  it('older German wording still localises (stale server, old session log)', () => {
    // Deliberately the retired producer string: a server one release behind, or a
    // session log recorded before the wording moved to English, must still render
    // a localised phase instead of leaking the raw line.
    expect(localizeActivityLabel("📝 Name 'pdf' existiert → 'pdf-2'", de)).toBe('Name pdf → pdf-2')
  })

  it('renders the live string through the real de/en bundles', () => {
    const deInst = createInstance('de')
    const enInst = createInstance('en')
    const renderDe = localizeActivityLabel(NAME_EXISTS_PHASE, (k, o) => deInst.t(k, o))
    const renderEn = localizeActivityLabel(NAME_EXISTS_PHASE, (k, o) => enInst.t(k, o))
    const fill = (template: string) =>
      template.replace('{{name}}', 'pdf').replace('{{unique}}', 'pdf-2')

    // Both named groups have to reach the bundle templates.
    expect(renderDe).toBe(fill(deLocale.chat.phaseNameExists))
    expect(renderEn).toBe(fill(enLocale.chat.phaseNameExists))
    expect(renderDe).toContain('pdf-2')
    expect(renderEn).toContain('pdf-2')
    // The English UI must not show German from a phase the backend sends in English.
    expect(renderDe).not.toBe(NAME_EXISTS_PHASE)
    expect(renderEn).not.toMatch(/existiert|„|“/)
  })
})
