/**
 * Ephe — activity label localization (AI-client parity, G8)
 *
 * The backend sends `activity` events with phase strings from
 * core/chat.py / core/skill_builder.py (language-neutral EN). Known phases are
 * turned into i18n keys here; EVERYTHING ELSE (tool commands such as
 * `web_search(query=…)`, skill paths, chart labels) stays
 * unchanged — forward compatibility: unknown = passthrough.
 *
 * Pure function (t injected) → testable without i18n initialization,
 * the same pattern as thinking.ts.
 */

type Translator = (key: string, opts?: Record<string, unknown>) => string

interface Rule {
  re: RegExp
  key: string
}

// Exactly the phase strings from core/chat.py + core/skill_builder.py
// (on_phase(…) over there). Move them when the backend changes.
const RULES: Rule[] = [
  { re: /^Analyzing request…$/, key: 'chat.phaseAnalyzing' },
  { re: /^Loading model… \(Retry\)$/, key: 'chat.phaseLoadingModel' },
  {
    re: /^Primary model needs more memory; retrying with (?<model>.+)…$/,
    key: 'chat.phaseFallbackModel',
  },
  { re: /^Tool round (?<round>\d+)…$/, key: 'chat.phaseToolRound' },
  { re: /^Processing results…$/, key: 'chat.phaseProcessing' },
  { re: /^Generating response…$/, key: 'chat.phaseGenerating' },
  { re: /^📚 Analyzing code patterns…$/, key: 'chat.phaseAnalyzingPatterns' },
  { re: /^💾 Saving skill…$/, key: 'chat.phaseSavingSkill' },
  {
    // The producer sends lowercase `name … exists` (core/skill_builder.py, 📝 phase);
    // the retired German `Name … existiert` stays accepted for one release, so a
    // server one build behind — or an older session log — still localises instead
    // of showing the raw wire string. Only the noun is matched case-insensitively:
    // the whole pattern is not, so no other rule can widen by accident.
    re: /^📝 [Nn]ame '(?<name>.+)' (?:exists|existiert) → '(?<unique>.+)'$/,
    key: 'chat.phaseNameExists',
  },
]

/**
 * Translates the known backend phase labels into the active UI language.
 * Unknown labels (tool commands, artifact labels) → unchanged.
 */
export function localizeActivityLabel(label: string, t: Translator): string {
  for (const { re, key } of RULES) {
    const m = label.match(re)
    if (!m) continue
    return m.groups ? t(key, m.groups) : t(key)
  }
  return label
}
