/** The mode button must not speak English just because a text is missing.
 *
 * Finding from the review walk (screenshot): the surface stood in German, the composer
 * chip in English — „Full access". The title comes from the hint text
 * (`chat.modeHint.<modus>`, everything before the em dash); the two modes
 * `edit-auto` and `full-access` had a hint in **no** language, and
 * `modeShortLabel` fell back to the English `fallback`.
 *
 * Such keys are dynamic (`t(\`chat.modeHint.${key}\`)`) and therefore fall
 * through the static i18n lint. This file is the bar across the list
 * that it builds.
 */
import { describe, it, expect } from 'vitest'
import { COMPOSER_MODES } from './ComposerModeMenu'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

type Bundle = { chat: Record<string, Record<string, string>> }
const deChat = (de as unknown as Bundle).chat
const enChat = (en as unknown as Bundle).chat

describe('Composer-Modi: jeder Titel hat einen Text in beiden Sprachen', () => {
  it.each(COMPOSER_MODES.map((m) => [m.key, m] as const))('%s', (_key, mode) => {
    const pfad = (key: string): [string, string] => {
      const [gruppe = '', schluessel = ''] = key.replace('chat.', '').split('.')
      return [gruppe, schluessel]
    }
    const [hintGruppe, hintSchluessel] = pfad(mode.hintKey)
    const [secGruppe, secSchluessel] = pfad(mode.sectionKey)
    for (const [sprache, chat] of [
      ['de', deChat],
      ['en', enChat],
    ] as const) {
      const hinweis = chat[hintGruppe]?.[hintSchluessel]
      expect(hinweis, `${sprache}: ${mode.hintKey} fehlt`).toBeTruthy()
      expect(chat[secGruppe]?.[secSchluessel], `${sprache}: ${mode.sectionKey} fehlt`).toBeTruthy()
      // The title is the first part of the hint — it must not be the
      // English remainder message when the surface is German.
      const titel = (hinweis ?? '').split(' — ')[0] ?? ''
      expect(titel.length, `${sprache}: Titel zu lang für den Chip`).toBeLessThanOrEqual(24)
      if (sprache === 'de') expect(titel).not.toBe(mode.fallback)
    }
  })
})

describe('Der Leerzustand nennt das Subjekt seiner Zeilen', () => {
  // „Zustand: Online" above „Modell: gemma4:12b (offline)" — two rows, one // language-gate: ignore — the superseded German row labels this test bars (de.json:1350 reads "Engine erreichbar")
  // word, two meanings. The upper row talks about the engine, so it names the engine.
  it('redet in der Engine-Zeile von der Engine, nicht vom Zustand', () => {
    const w = (de as unknown as { welcome: Record<string, string> }).welcome
    expect(w.modelOnline).toContain('Engine')
    expect(w.modelOnline).not.toMatch(/Zustand|State/)
    expect(w.modelOffline).toContain('Engine')
  })
})
