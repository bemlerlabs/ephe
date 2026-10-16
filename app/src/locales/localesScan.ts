/**
 * Locale gate — three classes that keep the German locale files clean for good.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * The three classes are not invented rules but proven breakages
 * (as of 2026-10-05, wave "P1 Sprache"): // language-gate: ignore — "P1 Sprache" is that wave's own name, quoted verbatim
 *
 * (a) SINGLE-BRACE PLACEHOLDERS. i18next only substitutes `{{word}}`; anything with
 *     single braces reaches the user verbatim. Field evidence: the migration preview
 *     on the knowledge page showed
 *     "Index → Archiv · {source} Merksätze in der Quelle" while the endpoint had long // language-gate: ignore — quoted product copy, kept verbatim
 *     since been delivering `source_total: 43` (/api/memory/migrate, dry_run). Six
 *     keys were affected — in BOTH files, because the en file is fed by the same
 *     copy-paste reflex. No test ever checked it.
 *
 * (b) DYNAMICALLY BUILT KEYS. `src/lib/i18n-keys.test.ts` checks only the keys where
 *     a t call carries a string literal and deliberately skips composed keys
 *     ("cannot be checked statically"). Through exactly that gap `settings.deep`
 *     entered the command palette: the palette sits there among German labels.
 *     This gate resolves the families from the code (TabKey, NAV, SETTINGS_NAV_KEYS,
 *     SECTION_TAB, Tab) and checks them against both files.
 *
 * (c) TRANSCRIBED UMLAUTS. "Server hinzufuegen" among "Server hinzufügen" neighbours, // language-gate: ignore — both spellings are the fixture this class compares
 *     "Aehnlichkeit", "Gekuerzt", "waehrend": ASCII spellings the user reads as // language-gate: ignore — continuation of the fixture spellings this class compares
 *     typos in their own interface. The test is therefore deliberately NARROW — the
 *     specificity fixtures below push back: `Kohlenmonoxid`, paths like
 *     `/Users/beispiel/Strasse/projekt` and base64/sha hash values must not fail. // language-gate: ignore — fixture path quoted verbatim from the tests below
 *     Otherwise nobody can satisfy the rule.
 */
import { expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/* ------------------------------------------------------------------ */
/* Material                                                            */
/* ------------------------------------------------------------------ */

export const read = (rel: string): string =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

export const deRaw = read('./de.json')
export const enRaw = read('./en.json')
export const de = JSON.parse(deRaw) as Record<string, unknown>
export const en = JSON.parse(enRaw) as Record<string, unknown>

/** Leaves of a resource as [path, value] pairs; arrays count with an index path. */
export function leaves(node: unknown, prefix = ''): Array<[string, string]> {
  if (typeof node === 'string') return [[prefix, node]]
  if (Array.isArray(node)) return node.flatMap((item, i) => leaves(item, `${prefix}.${i}`))
  if (node && typeof node === 'object')
    return Object.entries(node).flatMap(([k, v]) => leaves(v, prefix ? `${prefix}.${k}` : k))
  return []
}

export const deLeaves = leaves(de)
export const enLeaves = leaves(en)

/**
 * Does the key exist at runtime? `leaves()` joins every path with dots, so both
 * nested objects AND the flat dotted keys of the inventory
 * ("deepSection.chat", "plugins.orphans") are covered — that is exactly how
 * i18next resolves.
 */
export function keySet(entries: Array<[string, string]>): Set<string> {
  return new Set(entries.map(([k]) => k))
}
export const deKeys = keySet(deLeaves)
export const enKeys = keySet(enLeaves)

export function hasKey(keys: Set<string>, dotted: string): boolean {
  // i18next plurals: the code calls the base form, the file carries _one/_other.
  return keys.has(dotted) || keys.has(`${dotted}_one`) || keys.has(`${dotted}_other`)
}

/* ------------------------------------------------------------------ */
/* Class (a): single-brace {placeholder}                               */
/* ------------------------------------------------------------------ */

/**
 * Finds `{word}` in single braces. Doubles are stripped first so that
 * `{{count}}` does not pass as two single-brace placeholders.
 */
export function singleBraces(value: string): string[] {
  const stripped = value.replace(/\{\{[^{}]*\}\}/g, '\u0000')
  return [...stripped.matchAll(/\{\s*([A-Za-z_][\w.]*)\s*\}/g)].map((m) => `{${m[1]}}`)
}

export function singleBraceViolations(entries: Array<[string, string]>): string[] {
  return entries.flatMap(([key, value]) => {
    const found = singleBraces(value)
    return found.length ? [`${key}: ${found.join(', ')} — "${value}"`] : []
  })
}

/* ------------------------------------------------------------------ */
/* Class (b): dynamically built keys                              */
/* ------------------------------------------------------------------ */

/** Members of an `export type X = | 'a' | 'b'` union, read line by line. */
export function unionMembers(src: string, typeName: string): string[] {
  const start = src.indexOf(`export type ${typeName} =`)
  if (start < 0) throw new Error(`Typ ${typeName} nicht gefunden — Gate an die Quelle anpassen.`)
  const out: string[] = []
  for (const line of src.slice(start).split('\n').slice(1)) {
    const t = line.trim()
    if (!t.startsWith('|')) {
      if (out.length > 0) break
      continue
    }
    const m = /'([^']+)'/.exec(t)
    if (m?.[1]) out.push(m[1])
  }
  expect(out.length, `Vereinigung ${typeName} ist leer — Auflösung kaputt.`).toBeGreaterThan(0)
  return out
}

/** Literals from an array block, e.g. `SETTINGS_NAV_KEYS = [ 'a', … ] as const`. */
export function arrayLiterals(src: string, declaration: string, terminator: string): string[] {
  const start = src.indexOf(declaration)
  if (start < 0) throw new Error(`Deklaration ${declaration} nicht gefunden.`)
  const end = src.indexOf(terminator, start)
  const block = src.slice(start, end < 0 ? undefined : end)
  const out = [...block.matchAll(/'([^']+)'/g)].map((m) => m[1]).filter((s): s is string => !!s)
  expect(out.length, `Block ${declaration} ist leer — Auflösung kaputt.`).toBeGreaterThan(0)
  return out
}

/** Keys of a record block (`SECTION_TAB: Record<string, TabKey> = { … }`). */
export function recordKeys(src: string, declaration: string): string[] {
  const start = src.indexOf(declaration)
  if (start < 0) throw new Error(`Block ${declaration} nicht gefunden.`)
  const end = src.indexOf('\n}', start)
  const block = src.slice(start, end < 0 ? undefined : end)
  const out = [...block.matchAll(/^\s{2}([A-Za-z][\w-]*):/gm)]
    .map((m) => m[1])
    .filter((s): s is string => !!s)
  expect(out.length, `Block ${declaration} ist leer — Auflösung kaputt.`).toBeGreaterThan(0)
  return out
}

export const tabKeys = unionMembers(read('../components/dashboard/settings/types.ts'), 'TabKey')
export const navKeys = arrayLiterals(
  read('../components/dashboard/settings/types.ts'),
  'export const NAV_KEYS = [',
  '] as const',
)
// W10: the palette's settings rows ARE the navigation rows now — the tab keys live in
// the one list (NAV_KEYS in settings/types.ts) and both the panel and
// hooks/paletteExtraItems.ts read it, so the family is resolved once.
export const registerSections = recordKeys(
  read('../components/dashboard/settings/model/deepRegister.ts'),
  'export const SECTION_TAB: Record<string, TabKey> = {',
)
export const panelTabs = unionMembers(read('../components/dashboard/agent/primitives.tsx'), 'Tab')

export const upperFirst = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1)

/**
 * Documented exceptions: keys the code composes but which point at nothing.
 * They are reported, not removed — the palette is not this gate's file. The
 * exception invalidates itself: as soon as the key gets a real section
 * (TabKey/NAV), the gate demands it in the locales too.
 */
export const DEAD_ENTRIES: Record<string, string> = {
  'settings.deep':
    'src/hooks/paletteExtraItems.ts SETTINGS_NAV_KEYS nennt "deep"; TabKey, NAV und die section-Zuordnung in settings/model.tsx kennen kein "deep" — der Eintrag öffnet eine leere Fläche. Gemeldet am 2026-10-05.',
}

export function dynamicKeyDemands(): Array<{ key: string; from: string }> {
  const demands: Array<{ key: string; from: string }> = []
  for (const k of tabKeys)
    demands.push({ key: `settings.${k}`, from: 'TabKey (settings/types.ts)' })
  for (const k of navKeys) demands.push({ key: `settings.${k}`, from: 'NAV (settings/model.tsx)' })
  for (const k of registerSections)
    demands.push({ key: `settings.deepSection.${k}`, from: 'SECTION_TAB (deepRegister.ts)' })
  for (const k of panelTabs) {
    const cap = upperFirst(k)
    demands.push({ key: `agentPanel.tab${cap}`, from: 'Tab (agent/primitives.tsx)' })
    demands.push({
      key: `agentPanel.tabTip${cap}.title`,
      from: 'tabChrome tipKey (agent/tabChrome.ts)',
    })
    demands.push({
      key: `agentPanel.tabTip${cap}.body`,
      from: 'tabChrome tipKey (agent/tabChrome.ts)',
    })
  }
  return demands
}

/* ------------------------------------------------------------------ */
/* Class (c): transcribed umlauts                                     */
/* ------------------------------------------------------------------ */

/**
 * Everything that is not prose is stripped before the check: paths, URLs,
 * file names, `{{placeholder}`, code in backticks and command sequences. That
 * is exactly what this line is for — "'Strasse' inside a path" is a path, not a
 * heading, and base64 hash values appear in paths and manifests.
 */
export const NON_PROSE =
  /(?:https?:\/\/|file:\/\/|~\/|\.{1,2}\/|\/[\w.@+-]+(?:\/[\w.@+-]+)+|[\w@-]+\.(?:tsx?|jsx?|py|md|json|ya?ml|toml|sh|css|scss|html|db|sqlite|lock|zip|tgz|png|svg)\b|`[^`]*`|\{\{[^{}]*\}\}|[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)+)/g

/**
 * Transcribed umlauts are only recognised when looking at a pure ASCII word: a
 * word that itself carries ä/ö/ü/ß is already correct ("übersteuern" contains
 * "ue" and is still right). On top, at least 4 letters must be present —
 * otherwise hash fragments ("…8ae…", "Oe") would fail.
 */
export const TRANSCRIPTION = /(?:ae|oe|ue)/i
export const HEX_ONLY = /^[0-9a-fA-F]+$/

/**
 * Technical and loanwords that really spell ae|oe|ue. Anyone adding here also
 * writes why the word is not a transcription — the list is the excuse, not a
 * free pass.
 */
export const AE_OE_UE_ALLOW = new Set([
  'aktuell',
  'aktuelle',
  'aktuellen',
  'aktueller',
  'aktuelles',
  'dauer',
  'dauermodus',
  'dauert',
  'dauerte',
  // the infinitive of the same stem ("kann einige Minuten dauern") — not a
  // transcription of "dauern" with an umlaut, there is none
  'dauern',
  'genau',
  'genaue',
  'genauen',
  'genaueste',
  'genauesten',
  'manuell',
  'manuelle',
  'manuellen',
  'neue',
  'neuem',
  'neuen',
  'neuer',
  'neues',
  'neueste',
  'neuesten',
  'quelle',
  'quellen',
  'quellenliste',
  'steuern',
  'steuerung',
  'steuerungen',
  'zuerst',
  // "der Kern feuert dieses Event" — a real German word, not a transcription  <!-- language-gate: ignore (the quoted sample the stopword entry documents) -->
  'feuert',
  'feuere',
  'feuern',
  'gefeuert',
  // Technical names of the cell and engine runtime (AGENTS.md: MCP, API, token …)
  'fuel',
  'queue',
  'queues',
  'value',
  'values',
  'unique',
  'knoten',
])

/**
 * ss/ß: there is no general criterion — after a short vowel "ss" is correct
 * German (Fluss, Schloss, dass, muss). A blanket ss rule could be satisfied by
 * nobody, so what stands here is the set of stems whose standard spelling
 * requires a ß.
 */
export const SHARP_S_WORDS = [
  'aussen',
  'ausser',
  'ausserdem',
  'ausserhalb',
  'ausserte',
  'ausserstande',
  'strasse',
  'strassen',
  'gross',
  'grosse',
  'grossen',
  'groesser',
  'grosses',
  'mass',
  'masse',
  'massen',
  'fuss',
  'gruss',
  'grusse',
  'grussen',
  'weiss',
  'weisse',
  'weissen',
  'heiss',
  'heisse',
  'heissen',
  'liess',
]

/**
 * Known mutilated forms: here the umlaut itself is missing, not just the
 * transcription ("offnen" instead of "öffnen"). No rule in the world catches
 * that, so it stands here as a dictionary — with the finding that produced it.
 */
export const MUTILATED: Record<string, string> = {
  offnen: 'öffnen',
  ahnlich: 'ähnlich',
  ahnliche: 'ähnliche',
  ahnlichen: 'ähnlichen',
  ahnlichkeit: 'Ähnlichkeit',
  ahnlichkeiten: 'Ähnlichkeiten',
}

export function asciiWords(value: string): string[] {
  const prose = value.replace(NON_PROSE, ' ')
  return (prose.match(/[A-Za-zÄÖÜäöüß]+/g) ?? []).filter((w) => w.length >= 4)
}

export function transcriptionViolations(entries: Array<[string, string]>): string[] {
  const out: string[] = []
  for (const [key, value] of entries) {
    for (const word of asciiWords(value)) {
      if (!/^[A-Za-z]+$/.test(word)) continue // carries ä/ö/ü/ß -> already correct
      if (HEX_ONLY.test(word)) continue
      const lower = word.toLowerCase()
      if (TRANSCRIPTION.test(word) && !AE_OE_UE_ALLOW.has(lower))
        out.push(`${key}: "${word}" — Umschreibung, nicht Fachwort`)
      if (MUTILATED[lower]) out.push(`${key}: "${word}" — richtig: "${MUTILATED[lower]}"`)
      if (SHARP_S_WORDS.includes(lower)) out.push(`${key}: "${word}" — Standardschreibung mit ß`)
    }
  }
  return out
}

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */
