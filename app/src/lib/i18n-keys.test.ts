/**
 * i18n key lint (finding 2026-10-02): every `t('…')` literal has to exist in
 * `de.json` AND `en.json` — otherwise the raw path leaks into the UI. A template
 * whose variable stands first (`t(\`${tipKey}.title\`)`) is resolved through the
 * record that fills the variable, so the family is checked instead of skipped.
 */
import { describe, it, expect } from 'vitest'
import i18next from 'i18next'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

// Eager raw import of all source files (without test specs) — Vite delivers them to
// us as strings, no fs needed, runs even in the jsdom environment.
const sources = import.meta.glob<string>('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const STATIC_T = /(?<![A-Za-z0-9_$.])t\(\s*['"]([^'"\n]+)['"]/g
const TEST_FILE = /\/[^/]+\.(test|spec)\.[tm]sx?$/
const BANNED_PREFIX = ['@/', 'src/']

function extractKeys(): Map<string, string> {
  const hits = new Map<string, string>()
  for (const [p, raw] of Object.entries(sources)) {
    if (TEST_FILE.test(p)) continue
    for (const m of raw.matchAll(STATIC_T)) {
      const key = m[1]
      if (!key || BANNED_PREFIX.some((b) => key.startsWith(b))) continue
      if (!hits.has(key)) hits.set(key, p)
    }
  }
  return hits
}

const NAMESPACES = new Set(Object.keys(de))
const LOCALE_FILES = new Set(['de.json', 'en.json'])
const corpus = Object.entries(sources).filter(
  ([p]) => !TEST_FILE.test(p) && !LOCALE_FILES.has(p.split('/').pop() ?? ''),
)
const corpusText = corpus.map(([, raw]) => raw).join('\n')

/**
 * Record declarations whose values name locale keys — the `familyTipKey` shape.
 * Only values inside a bundle namespace count, so an ordinary options object
 * cannot feed the lint.
 */
function mapDeclarations(from: string): Map<string, string[]> {
  const out = new Map<string, string[]>()
  const decl = /(?:const|let)\s+([A-Za-z_$][\w$]*)\s*(?::\s*Record<[^>]+>)?\s*=\s*\{/g
  for (const m of from.matchAll(decl)) {
    let depth = 0
    let end = -1
    const open = (m.index ?? 0) + m[0].length - 1
    for (let i = open; i < from.length; i++) {
      if (from[i] === '{') depth += 1
      else if (from[i] === '}') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) continue
    const values = [...from.slice(open + 1, end).matchAll(/:\s*(['"])([^'"]+)\1/g)]
      .map((v) => v[2] ?? '')
      .filter((v) => !v.includes('$') && NAMESPACES.has(v.split('.')[0] ?? ''))
    if (values.length) out.set(m[1] ?? '', values)
  }
  return out
}

/** `t(\`${var}.suffix\`)` — the variable-first template neither gate could see. */
function variableFirstTemplates(): Array<{ name: string; suffix: string; file: string }> {
  const out: Array<{ name: string; suffix: string; file: string }> = []
  for (const [file, raw] of corpus) {
    for (const m of raw.matchAll(/(?<![A-Za-z0-9_$.])t\(\s*`([^`]*)`\s*\)/g)) {
      const hit = /^\$\{([A-Za-z_$][\w$]*)\}([^`]*)$/.exec(m[1] ?? '')
      if (hit) out.push({ name: hit[1] ?? '', suffix: hit[2] ?? '', file })
    }
  }
  return out
}

/** The values behind a template variable — the map itself, or the map it indexes. */
function valuesFor(name: string, maps: Map<string, string[]>): string[] {
  const direct = maps.get(name)
  if (direct) return direct
  const alias = new RegExp(`(?:const|let)\\s+${name}\\s*=\\s*([^\\n]+)`).exec(corpusText)
  if (!alias) return []
  const expression = alias[1] ?? ''
  const mapName = /^\s*([A-Za-z_$][\w$]*)\[/.exec(expression)?.[1]
  const values = mapName ? [...(maps.get(mapName) ?? [])] : []
  for (const m of expression.matchAll(/'([A-Za-z][\w.-]*(?:\.[\w-]+)+)'/g))
    if (NAMESPACES.has((m[1] ?? '').split('.')[0] ?? '')) values.push(m[1] ?? '')
  return [...new Set(values)]
}

function createInstance(lng: 'de' | 'en') {
  const inst = i18next.createInstance()
  // init is async — no synchronous detour via .use(initReactI18next)
  // needed, the pure exists() check only requires resources.
  void inst.init({
    resources: { de: { translation: de }, en: { translation: en } },
    lng,
    fallbackLng: lng,
    supportedLngs: [lng],
    interpolation: { escapeValue: false },
  })
  return inst
}

describe('i18n key lint — alle t()-Literals in de.json und en.json', () => {
  const keys = extractKeys()
  // exists() captures the i18next runtime semantics: nested OR
  // flat dot key, plus the plural variants (_one/_other).
  const deInst = createInstance('de')
  const enInst = createInstance('en')
  const present = (inst: ReturnType<typeof createInstance>, k: string) =>
    inst.exists(k) || inst.exists(`${k}_one`) || inst.exists(`${k}_other`)

  it('findet mindestens 200 Statische t()-Keys im Quellcode', () => {
    expect(keys.size).toBeGreaterThanOrEqual(200)
  })

  it('jeder t()-Key existiert in de.json', () => {
    const missing: string[] = []
    for (const [k, file] of keys) if (!present(deInst, k)) missing.push(`${k}  ←  ${file}`)
    expect(missing).toEqual([])
  })

  it('jeder t()-Key existiert in en.json', () => {
    const missing: string[] = []
    for (const [k, file] of keys) if (!present(enInst, k)) missing.push(`${k}  ←  ${file}`)
    expect(missing).toEqual([])
  })

  it('der Bestand ungenutzter Schlüssel wächst nicht (Schulden-Ratsche)', () => {
    // Measurement rule: dead means the full key sits in no source outside the
    // language files, no dynamic pattern (`t(\`artifacts.kind.${key}\`)`) can
    // reach it, and no resolved map holds it. Keys in a record are references
    // here because the template test below resolves the template that reads it.
    const lits = new Set<string>(
      [...corpusText.matchAll(/['"`]([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_$[\]-]+)+)/g)].map(
        (m) => m[1] ?? '',
      ),
    )
    const maps = mapDeclarations(corpusText)
    for (const values of maps.values()) for (const value of values) lits.add(value)
    for (const { name, suffix } of variableFirstTemplates())
      for (const value of valuesFor(name, maps)) lits.add(`${value}${suffix}`)
    const dyn = new Set<string>(
      [...corpusText.matchAll(/['"`]([A-Za-z0-9_.$-]*?)(?:\$\{|\s*\+)/g)]
        .map((m) => m[1] ?? '')
        .filter(Boolean),
    )
    const leaves: string[] = []
    const walk = (obj: unknown, pre: string) => {
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        const key = pre ? `${pre}.${k}` : k
        if (v && typeof v === 'object') walk(v, key)
        else leaves.push(key.replace(/_(one|other|two|few|many)$/, ''))
      }
    }
    walk(de, '')
    const dead = [...new Set(leaves)].filter(
      (k) =>
        ![...lits].some((L) => L === k || L.startsWith(`${k}.`)) &&
        ![...dyn].some((P) => k.startsWith(P)),
    )
    // 2026-11-11: the 13 remaining leaves (streamGroup, discover.badge) and the
    // empty taskDock object were removed; a new dead key is a regression.
    if (process.env.EPHE_TOTE_LISTE) console.log('TOT:', dead.join('\n') || 'keine')
    expect(dead).toEqual([])
  })

  it('resolves a variable prefix through its record map', () => {
    const maps = mapDeclarations(corpusText)
    const templates = variableFirstTemplates()
    expect(templates.length).toBeGreaterThan(0)
    const missing: string[] = []
    for (const { name, suffix, file } of templates) {
      const values = valuesFor(name, maps)
      expect(values.length, `no map for ${name} (${file})`).toBeGreaterThan(0)
      for (const value of values) {
        const key = `${value}${suffix}`
        if (!present(deInst, key)) missing.push(`${key}  ←  de, ${file}`)
        if (!present(enInst, key)) missing.push(`${key}  ←  en, ${file}`)
      }
    }
    expect(missing).toEqual([])
  })

  it('de- und en-Schluessel sind deckungsgleich (keine einseitigen Ergaenzungen)', () => {
    // Uses the recursive key set of both trees; plural suffixes normalize to
    // their base so that "_one"/"_other" do not count twice.
    const leafPaths = (obj: unknown, prefix = '', out = new Set<string>()): Set<string> => {
      if (obj === null || typeof obj !== 'object') {
        if (prefix) out.add(prefix.replace(/_(one|two|few|many|other)$/, ''))
        return out
      }
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        // A flat dotted key like "plugins.orphans" is handled like a leaf
        // (i18next resolves it at runtime through this path).
        if (typeof v === 'string')
          out.add(`${prefix ? prefix + '.' : ''}${k}`.replace(/_(one|two|few|many|other)$/, ''))
        else leafPaths(v, `${prefix ? prefix + '.' : ''}${k}`, out)
      }
      return out
    }
    const deKeys = leafPaths(de)
    const enKeys = leafPaths(en)
    const onlyDe = [...deKeys].filter((k) => !enKeys.has(k))
    const onlyEn = [...enKeys].filter((k) => !deKeys.has(k))
    expect({ onlyDe, onlyEn }).toEqual({ onlyDe: [], onlyEn: [] })
  })
})

/**
 * Locale leak lint (finding 2026-10-08): `ActivityFeed.tsx` rendered its overflow
 * counter as a German text node — `… {overflow} weitere` — so the label never followed
 * the language switch. The lint above only reads `t()` calls and is blind to a text
 * node; this is its second half: a guarded component may hold no word that stands only
 * in `de.json`.
 *
 * The vocabulary is derived from the two shipped bundles (every token of 4+ lowercase
 * letters out of a de value, minus every token of an en value — the same "de-only
 * lexicon" that signal 3 of `docs/GERMAN_LITERALS_2026-10-08.md` measures with), never
 * from a hand-written word list. Comments are stripped before the scan: they are
 * developer prose, never the surface.
 *
 * The list is a ratchet: buckets 1 and 2 of that inventory are still open
 * in other source files, so a file joins the list once its own surface runs through `t()`
 * or an English-but-dead `defaultValue`.
 */
const LEAK_GUARDED = [
  'components/dashboard/ActivityFeed.tsx',
  // Wave #55 (2026-10-09): the Skills rows read their labels through t(); the
  // built-in chip was the last hardwired word there.
  'components/dashboard/settings/model/sections-capabilities.tsx',
  // Wave #55: the crash screen.
  'components/ui/ErrorBoundary.tsx',
  // WS7-45 (2026-10-11): the composer/reader keep-awake surfaces. Their last
  // German literals were `defaultValue` fallbacks — dead for a resolved key, but
  // a German last resort for one that goes missing; now English.
  'components/dashboard/chat/ModeMenu.tsx',
  'components/dashboard/chat/HeaderModeControl.tsx',
  'components/dashboard/chat/ComposerAccessControl.tsx',
  'components/dashboard/chat/modeCatalog.ts',
  'components/dashboard/chat/ComposerModelMenu.tsx',
  'components/dashboard/chat/ComposerAttachMenu.tsx',
  'components/dashboard/KeepAwakeToggle.tsx',
  'components/dashboard/agent/readerView.tsx',
  'components/dashboard/ChatInput.tsx',
]

const TOKEN = /[a-zäöüß]{4,}/g

function tokensOf(node: unknown, out = new Set<string>()): Set<string> {
  if (typeof node === 'string')
    for (const word of node.toLowerCase().match(TOKEN) ?? []) out.add(word)
  else if (Array.isArray(node)) node.forEach((item) => tokensOf(item, out))
  else if (node && typeof node === 'object')
    Object.values(node).forEach((item) => tokensOf(item, out))
  return out
}

/** Words the German bundle knows and the English one does not: product German. */
const deOnly = (() => {
  const words = tokensOf(de)
  for (const word of tokensOf(en)) words.delete(word)
  return words
})()

const withoutComments = (src: string) =>
  src.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/\/\/[^\n]*/g, ' ')

function germanLeaks(src: string): string[] {
  const tokens = withoutComments(src).toLowerCase().match(TOKEN) ?? []
  return [...new Set(tokens.filter((word) => deOnly.has(word)))]
}

function sourceOf(rel: string): string {
  const hit = Object.entries(sources).find(([p]) => p.endsWith(rel))
  if (!hit) throw new Error(`${rel} is not in the source glob — update the gate path.`)
  return hit[1]
}

describe('locale leak — jede guarded Quelle zeigt ihre Labels durch t()', () => {
  it('der Wortschatz kommt aus den Bundles und kennt „weitere"', () => {
    expect(deOnly.size).toBeGreaterThan(500)
    expect(deOnly.has('weitere')).toBe(true)
    // a token of the English bundle is never a leak
    expect(deOnly.has('more')).toBe(false)
  })

  it('jede guarded Datei bleibt frei von de-only Wörtern', () => {
    const hits = LEAK_GUARDED.flatMap((rel) =>
      germanLeaks(sourceOf(rel)).map((word) => `${rel}: ${word}`),
    )
    expect(hits).toEqual([])
  })

  it('Gegenprobe: der alte Textnode aus ActivityFeed fällt wieder auf', () => {
    // The exact shape of the 2026-10-08 defect, planted back into a fixture.
    expect(germanLeaks('<div>\n  … {overflow} weitere\n</div>')).toEqual(['weitere'])
  })
})
