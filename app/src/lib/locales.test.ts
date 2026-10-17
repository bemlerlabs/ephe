/**
 * Locale gate — three classes that keep the German language files clean for good.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * The three classes are not invented rules but proven breakage sites
 * (as of 2026-10-05, wave "P1 Sprache"): // language-gate: ignore — "P1 Sprache" is that wave's own name, quoted verbatim
 *
 * (a) SINGLE-BRACE PLACEHOLDERS. i18next replaces `{{word}}` only; anything with
 *     single braces reaches the user verbatim. Proven in the field: the migration
 *     preview on the knowledge page showed
 *     "Index → Archiv · {source} Merksätze in der Quelle" even though the endpoint // language-gate: ignore — quoted product copy, kept verbatim
 *     had long been returning `source_total: 43` (/api/memory/migrate, dry_run). Six
 *     keys were affected — in BOTH files, because the en file is fed by the same
 *     copy-paste reflex. No test ever checked this.
 *
 * (b) DYNAMICALLY BUILT KEYS. `src/lib/i18n-keys.test.ts` checks the `t('…')`
 *     literals and deliberately leaves composed keys out ("cannot be checked
 *     statically"). That is exactly the gap `settings.deep` came through into the
 *     command palette: the palette hangs there between German labels.
 *     This gate resolves the families from the code (TabKey, NAV, SETTINGS_NAV_KEYS,
 *     SECTION_TAB, Tab) and checks them against both files.
 *
 * (c) UMLAUT TRANSLITERATIONS. "Server hinzufuegen" among "Server hinzufügen" // language-gate: ignore — both are the fixture spellings this class compares
 *     neighbours, "Aehnlichkeit", "Gekuerzt", "waehrend": ASCII spellings the user // language-gate: ignore — continuation of the fixture spellings this class compares
 *     reads as typos in their own interface. The test is therefore deliberately
 *     NARROW — the specificity fixtures below push back: `Kohlenmonoxid`, paths like
 *     `/Users/beispiel/Strasse/projekt` and base64/sha hashes must not fall over. // language-gate: ignore — fixture path quoted verbatim from the test below
 *     Otherwise nobody could satisfy the rule.
 */
import { describe, expect, it } from 'vitest'

/* ------------------------------------------------------------------ */
/* Material                                                            */
/* ------------------------------------------------------------------ */
import {
  DEAD_ENTRIES,
  de,
  deKeys,
  deLeaves,
  deRaw,
  dynamicKeyDemands,
  en,
  enKeys,
  enLeaves,
  hasKey,
  leaves,
  navKeys,
  singleBraceViolations,
  singleBraces,
  tabKeys,
  transcriptionViolations,
} from '../locales/localesScan'
describe('Klasse (a) — kein einzeiliger {platzhalter} in irgendeiner Ressource', () => {
  it('de.json hat keine einzeiligen Platzhalter', () => {
    expect(singleBraceViolations(deLeaves)).toEqual([])
  })

  it('en.json hat keine einzeiligen Platzhalter', () => {
    expect(singleBraceViolations(enLeaves)).toEqual([])
  })

  it('die sechs reparierten Stellen interpolieren jetzt wirklich', () => {
    // Before the fix: "Index → Archiv · {source} Merksätze in der Quelle" with source_total 43. // language-gate: ignore — the pre-fix German copy this test pins
    for (const key of [
      'memory.reportSource',
      'memory.migrated',
      'memory.correctedCount',
      'scheduler.deleteJob',
      'agentPanel.trajectoryTruncated',
      'header.checkoutDirtyConfirm',
    ]) {
      for (const [name, tree] of [
        ['de', de],
        ['en', en],
      ] as const) {
        const value = leaves(tree).find(([k]) => k === key)?.[1]
        expect(value, `${name}.json/${key} fehlt`).toBeTruthy()
        expect(singleBraces(value ?? ''), `${name}.json/${key} ist noch einzeilig`).toEqual([])
        expect(value).toMatch(/\{\{/)
      }
    }
  })

  it('Gegenprobe: der Detektor sieht eine eingebaute einzeilige Stelle', () => {
    expect(singleBraces('Index → Archiv · {source} Merksätze in der Quelle')).toEqual(['{source}'])
    expect(singleBraces('Beide {{doppelten}} bleiben unangetastet')).toEqual([])
    expect(singleBraces('Klammerpaare in Prosa: (n) bleiben auch heil')).toEqual([])
  })
})

describe('Klasse (b) — jeder im Code zusammengebaute Schlüssel existiert in beiden Dateien', () => {
  const demands = dynamicKeyDemands()

  it('die aufgelösten Familien sind grob so zahlreich wie der Bestand', () => {
    // Keeps the resolution growing: if a parser finds nothing any more, the gate is empty.
    expect(demands.length).toBeGreaterThan(60)
  })

  it('jeder dynamische Schlüssel steckt in de.json', () => {
    const missing = demands
      .filter(({ key }) => !DEAD_ENTRIES[key])
      .filter(({ key }) => !hasKey(deKeys, key))
      .map(({ key, from }) => `${key}  ←  ${from}`)
    expect(missing).toEqual([])
  })

  it('jeder dynamische Schlüssel steckt in en.json', () => {
    const missing = demands
      .filter(({ key }) => !DEAD_ENTRIES[key])
      .filter(({ key }) => !hasKey(enKeys, key))
      .map(({ key, from }) => `${key}  ←  ${from}`)
    expect(missing).toEqual([])
  })

  it('die Ausnahmeliste ist klein und jede Ausnahme ist wirklich tot', () => {
    const dead = Object.keys(DEAD_ENTRIES)
    expect(dead.length).toBeLessThanOrEqual(3)
    for (const key of dead) {
      const leaf = key.replace(/^settings\./, '')
      // Self-invalidation: once TabKey or NAV knows the name, the exception is
      // void and the gate demands the key in both files.
      const alive = tabKeys.includes(leaf) || navKeys.includes(leaf)
      expect(
        alive,
        `${key} ist nicht mehr tot — Ausnahme aus DEAD_ENTRIES streichen ` +
          `und den Schlüssel in de.json UND en.json nachziehen. Grund: ${DEAD_ENTRIES[key]}`,
      ).toBe(false)
      expect(
        hasKey(deKeys, key) || hasKey(enKeys, key),
        `${key} existiert doch — Ausnahme streichen.`,
      ).toBe(false)
    }
  })

  it('Gegenprobe: ein fehlender dynamischer Schlüssel fällt auf', () => {
    expect(hasKey(deKeys, 'settings.deep')).toBe(false)
    expect(hasKey(deKeys, 'settings.engine')).toBe(true)
    expect(hasKey(deKeys, 'agentPanel.tabTipMemory.title')).toBe(true)
    expect(hasKey(deKeys, 'agentPanel.tabTipEsGibtNichtSoEtwas.title')).toBe(false)
  })
})

describe('Klasse (c) — keine Umlaut-Umschreibung im deutschen File', () => {
  it('de.json schreibt keine Umschreibungen (hinzufuegen, Aehnlich, Gekuerzt, …)', () => {
    expect(transcriptionViolations(deLeaves)).toEqual([])
  })

  it('die gefundenen Stellen sind tatsächlich repariert', () => {
    const byKey = new Map(deLeaves)
    expect(byKey.get('settings.mcpAdd')).toBe('Server hinzufügen')
    expect(byKey.get('agentPanel.trajectoryTruncated')).toContain('Gekürzt')
    expect(byKey.get('agentPanel.trajectoryEmpty')).toContain('während')
    expect(byKey.get('common.apply')).toBe('Übernehmen')
    expect(byKey.get('slash.desc.skills')).toBe('Verfügbare Skills auflisten')
    expect(byKey.get('statusBar.storageHint')).toContain('Gerät')
    // Dictionary 2026-10-06: in the real surface the pane is named Browser, not
    // Vorschau. Only the umlaut spelling of „öffnen“ stays asserted here. // language-gate: ignore — the German label the next line asserts verbatim
    expect(byKey.get('chat.toolOpenPreview')).toBe('Im Browser öffnen')
  })

  it('Spezifität: Fachwörter, Pfade und Häshwerte bleiben heil', () => {
    // Nobody could satisfy the rule if these lines fell over.
    const harmless: Array<[string, string]> = [
      ['fixture.gift', 'Kohlenmonoxid ist ein Gas'],
      ['fixture.path', 'Datei liegt unter /Users/beispiel/Strasse/projekt/app.py'],
      ['fixture.hash', 'gepinntes sha256:8ae3f0c9d1b2e4a5c6d7f8091a2b3c4d'],
      ['fixture.b64', 'Inhalts-Hash AQF8ae3ZQkLmNpRsTuVwXy=='],
      ['fixture.tech', 'MCP, API, Token, Cron, Markdown, Skill, Plugin, Terminal, Browser'],
      ['fixture.words', 'Aktuelle Quelle der neuen Dauer: manuell zuerst genau steuern'],
      ['fixture.short', 'ss, ae, oe und ue als Einzellote gehen nicht durch'],
      ['fixture.kurz', 'Fluss, Schloss, dass, muss und Schluss sind korrektes Deutsch'],
    ]
    expect(transcriptionViolations(harmless)).toEqual([])
  })

  it('Gegenprobe: eingebaute Umschreibungen werden gemeldet', () => {
    const planted: Array<[string, string]> = [
      ['fixture.planted1', 'Server hinzufuegen'],
      ['fixture.planted2', 'Aehnlichkeit und Aehnlichkeitswert'],
      ['fixture.planted3', 'Duplikat ab (Ahnlichkeit)'],
      ['fixture.planted4', 'Gekuerzt, waehrend, geaendert, geloescht'],
      ['fixture.planted5', 'In Vorschau offnen'],
      ['fixture.planted6', 'Text nach aussen und von ausserhalb'],
    ]
    const found = transcriptionViolations(planted)
    const keys = new Set(found.map((line) => line.split(':')[0]))
    expect([...keys].sort()).toEqual(planted.map(([k]) => k).sort())
    expect(found.join('\n')).toContain('hinzufuegen')
    expect(found.join('\n')).toContain('Aehnlichkeit')
    expect(found.join('\n')).toContain('öffnen')
    expect(found.join('\n')).toContain('ß')
  })
})

describe('Bestand — der Gate läuft über das echte Material', () => {
  it('beide Dateien parsen und deckungsgleich viele Blätter haben', () => {
    expect(deLeaves.length).toBeGreaterThan(1000)
    expect(deLeaves.length).toBe(enLeaves.length)
  })

  it('das deutsche File enthält keine der reparierten Altlasten mehr', () => {
    for (const alt of [
      'hinzufuegen',
      'Gekuerzt',
      'waehrend',
      'Uebernehmen',
      'Aenderung',
      'Geraet',
      'offnen',
      'aussen',
    ]) {
      expect(deRaw, `Altlast ${alt} ist zurück`).not.toContain(alt)
    }
  })
})
