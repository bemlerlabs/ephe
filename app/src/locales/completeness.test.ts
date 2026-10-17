/**
 * WS7-44 — de.json completeness: every key the code uses exists in de.json AND en.json.
 *
 * The two neighbours answer only halves of this question. `lib/i18n-keys.test.ts`
 * reads the `t('…')` literal and leaves computed keys alone — so it never saw
 * `i18n.t('…')` (main, sessionSync, the chat stream, serverError) nor a key held
 * in data as `labelKey: 'shortcuts.palette'`. `lib/locales.test.ts` resolves five
 * settings families from the code; everything the interface else composes stays
 * unchecked. This gate takes the whole surface:
 *
 *   1. literals from every call form — `t(…)`, `i18n.t(…)`, backticks — plus the
 *      `*Key:` fields that name a key instead of inlining a t() call;
 *   2. the computed families whose value set the code itself declares: hook
 *      events, appearance themes, plugin segments, shortcut groups, engine
 *      states, setup options, the composer's permission badge, the memory and
 *      artifact views, automation template ids, the four welcome cards.
 *
 * A miss is not cosmetic: i18next hands the key back untouched, so the user
 * reads `settings.shortcutsGroup.composer` where a word belongs.
 *
 * The sources are read from disk when the test runs. An eager glob resolves its
 * matches during transform, so a file one of the agents editing this tree at the
 * same time creates and removes in between fails the whole suite on ENOENT.
 *
 * Read-only on ../lib/localesScan — this file adds a gate, it changes nothing.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { deKeys, enKeys, hasKey } from './localesScan'

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/de.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}
const SRC = findSrc()
const TEST_FILE = /\.(test|spec)\.[tm]sx?$/

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`
    if (entry.isDirectory()) walk(path, out)
    else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
      if (!TEST_FILE.test(entry.name)) out.push(path)
    }
  }
  return out
}

const byRel = new Map<string, string>()
for (const abs of walk(SRC)) {
  try {
    byRel.set(abs.slice(SRC.length + 1), readFileSync(abs, 'utf8'))
  } catch {
    // the file vanished between listing and reading — another agent owns it
  }
}

const NAMESPACES = new Set([...deKeys].map((k) => k.split('.')[0]))

/** `t('…')`, `i18n.t('…')`, `.t(\`…\`)` — any literal argument to a t() call. */
const CALL = /(?<![A-Za-z0-9_$])t\(\s*(['"`])([^'"`\n]*?)\1/g
/** `labelKey: 'shortcuts.palette'` — a key held in data, handed to t() later. */
const KEY_FIELD = /([A-Za-z]*[Kk]ey)\s*:\s*(['"`])([A-Za-z][\w.-]*(?:\.[\w-]+)+)\2/g

/** A key literal qualifies only in a known bundle namespace and without ${} in it. */
function qualifies(key: string): boolean {
  return !!key && !key.includes('$') && NAMESPACES.has(key.split('.')[0])
}

/** Every key suggestion one source file makes, whatever the call form. */
export function keysInSource(raw: string): string[] {
  const out: string[] = []
  for (const m of raw.matchAll(CALL)) out.push(m[2] ?? '')
  for (const m of raw.matchAll(KEY_FIELD)) out.push(m[3] ?? '')
  return out.filter(qualifies)
}

function staticDemands(): Map<string, string> {
  const hits = new Map<string, string>()
  for (const [file, raw] of byRel)
    for (const key of keysInSource(raw)) if (!hits.has(key)) hits.set(key, file)
  return hits
}

/* ------------------------------------------------------------------ */
/* Computed families the code declares — resolved from the source.     */
/* ------------------------------------------------------------------ */

function text(rel: string): string {
  const raw = byRel.get(rel)
  if (raw === undefined) throw new Error(`source ${rel} not found — adjust the resolver.`)
  return raw
}

/** A slice from `anchor` to the next `terminator`; the resolver's own fence. */
function block(rel: string, anchor: string, terminator: string): string {
  const src = text(rel)
  const start = src.indexOf(anchor)
  if (start < 0) throw new Error(`anchor "${anchor}" gone from ${rel} — the family moved.`)
  const end = src.indexOf(terminator, start)
  return src.slice(start, end < 0 ? undefined : end)
}

const quoted = (s: string): string[] => [...s.matchAll(/'([^']+)'/g)].map((m) => m[1] as string)
const fieldLits = (s: string, name: string): string[] =>
  [...s.matchAll(new RegExp(`${name}:\\s*'([^']+)'`, 'g'))].map((m) => m[1] as string)

/** Union members of `export type X = 'a' | 'b'`. */
function unionMembers(rel: string, name: string): string[] {
  const m = new RegExp(`export type ${name} =([^\\n]+)`).exec(text(rel))
  if (!m) throw new Error(`union ${name} gone from ${rel} — the family moved.`)
  return quoted(m[1] as string)
}

/** Literals of a one-line field type: `approval_profile: 'strict' | 'session'`. */
function fieldUnion(rel: string, field: string): string[] {
  const m = new RegExp(`${field}:\\s*([^\\n]+)`).exec(text(rel))
  if (!m) throw new Error(`field union ${field} gone from ${rel} — the family moved.`)
  return quoted(m[1] as string)
}

/** The `([…] as const)` array driving a `.map((<var>) =>` loop. */
function loopArray(rel: string, varName: string): string[] {
  const m = new RegExp(`(\\[[^\\]]*\\])\\s*as const\\)\\s*\\.map\\(\\(${varName}\\)`).exec(
    text(rel),
  )
  if (!m) throw new Error(`loop array for ${varName} gone from ${rel} — the family moved.`)
  return quoted(m[1] as string)
}

const SET = 'components/dashboard/settings/model'

function dynamicDemands(): Array<{ key: string; from: string }> {
  const out: Array<{ key: string; from: string }> = []
  const add = (prefix: string, values: string[], from: string) => {
    if (values.length === 0)
      throw new Error(`family ${prefix} resolved empty (${from}) — it moved.`)
    for (const v of values) out.push({ key: `${prefix}.${v}`, from })
  }

  add(
    'settings.hooksEvent',
    quoted(block(`${SET}/sections-hooks.tsx`, 'const EVENT_ORDER = [', ']')),
    'EVENT_ORDER (sections-hooks.tsx)',
  )
  add(
    'settings.appearanceTheme',
    loopArray(`${SET}/sections-appearance.tsx`, 'mode'),
    'appearance themes (sections-appearance.tsx)',
  )
  add(
    'settings.plugins',
    loopArray(`${SET}/sections-plugins.tsx`, 'seg'),
    'plugin segments (sections-plugins.tsx)',
  )
  add(
    'settings.shortcutsGroup',
    fieldLits(block(`${SET}/sections-shortcuts.tsx`, 'const GROUPS = [', '] as const'), 'key'),
    'GROUPS (sections-shortcuts.tsx)',
  )

  const engine = unionMembers('lib/api/types.ts', 'EngineState')
  add('settings.engineState', engine, 'EngineState (lib/api/types.ts)')
  add('setup.engineState', engine, 'EngineState (lib/api/types.ts)')

  add(
    'setup.option',
    fieldLits(block('pages/SetupPage.tsx', 'const OPTIONS:', '\n]'), 'kind'),
    'OPTIONS (pages/SetupPage.tsx)',
  )
  add(
    'memory.view',
    quoted(block('pages/MemoryPage.tsx', 'const VIEWS = [', '] as const')),
    'VIEWS (pages/MemoryPage.tsx)',
  )
  add(
    'artifacts.page.view',
    quoted(block('pages/ArtifactsPage.tsx', 'const VIEWS = [', '] as const')),
    'VIEWS (pages/ArtifactsPage.tsx)',
  )

  // chat.perm.<profile>: the security profile the composer badge shows.
  add(
    'chat.perm',
    fieldUnion('lib/api/types_extra.ts', 'approval_profile'),
    'approval_profile (lib/api/types_extra.ts)',
  )

  // automation.template.<id>.{title,task,cadence}
  const templateIds = fieldLits(
    block('components/dashboard/SchedulerPanel.tsx', 'const AUTOMATION_TEMPLATES', '\n]'),
    'id',
  )
  for (const id of templateIds)
    for (const field of ['title', 'task', 'cadence'])
      out.push({ key: `automation.template.${id}.${field}`, from: 'AUTOMATION_TEMPLATES' })

  // welcome.cards.<i>.{title,prompt}: as many cards as CARD_ICONS declares.
  const cards = block(
    'components/dashboard/WelcomeEmptyState.tsx',
    'const CARD_ICONS = [',
    '] as const',
  )
  const cardCount = (cards.split('[')[1] ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean).length
  if (cardCount === 0) throw new Error('CARD_ICONS resolved empty — the welcome cards moved.')
  for (let i = 0; i < cardCount; i++)
    for (const field of ['title', 'prompt'])
      out.push({ key: `welcome.cards.${i}.${field}`, from: 'CARD_ICONS (WelcomeEmptyState.tsx)' })

  // streamGroup.<family>: the summary labels held in SUMMARY_KEY.
  for (const m of text('lib/toolStreamModel.ts').matchAll(/'(streamGroup(?:\.\w+)+)'/g))
    out.push({ key: m[1] as string, from: 'SUMMARY_KEY (lib/toolStreamModel.ts)' })

  return out
}

/* ------------------------------------------------------------------ */
/* Gates                                                               */
/* ------------------------------------------------------------------ */

describe('de.json completeness — every key the code uses exists in both bundles', () => {
  const statics = staticDemands()
  const dynamics = dynamicDemands()

  it('the static surface is broad enough to be this gate (guards the extractor)', () => {
    expect(statics.size).toBeGreaterThanOrEqual(900)
    // the call forms the neighbouring gate cannot read, proven present here
    expect(
      [...statics.keys()].some((k) => k === 'sw.updateAvailable' || k === 'sync.droppedTitle'),
    ).toBe(true)
  })

  it('every statically read key exists in de.json and en.json', () => {
    const missing: string[] = []
    for (const [key, file] of statics)
      if (!hasKey(deKeys, key) || !hasKey(enKeys, key)) missing.push(`${key}  ←  ${file}`)
    expect(missing).toEqual([])
  })

  it('the family resolvers found their anchors (guards the resolvers)', () => {
    expect(dynamics.length).toBeGreaterThanOrEqual(40)
  })

  it('every computed family key exists in de.json and en.json', () => {
    const missing = dynamics
      .filter((d) => !(hasKey(deKeys, d.key) && hasKey(enKeys, d.key)))
      .map((d) => `${d.key}  ←  ${d.from}`)
    expect(missing).toEqual([])
  })
})

describe('the extractor itself', () => {
  it('rules out a key that is not a bundle namespace', () => {
    expect(keysInSource("const x = t('zzz.notAKey')")).toEqual([])
  })

  it('surfaces a planted key in every call form it must read', () => {
    const planted = 'chat.plantedKeyThatNoBundleCarries'
    expect(keysInSource(`main.tsx: i18n.t('${planted}')`)).toContain(planted)
    expect(keysInSource(`x.t(\`${planted}\`)`)).toContain(planted)
    expect(keysInSource(`const row = { labelKey: '${planted}' }`)).toContain(planted)
  })

  it('the planted key is reported missing by this gate', () => {
    const planted = 'chat.plantedKeyThatNoBundleCarries'
    expect(hasKey(deKeys, planted) && hasKey(enKeys, planted)).toBe(false)
  })

  it('a key that exists passes the same predicate', () => {
    expect(hasKey(deKeys, 'chat.send') && hasKey(enKeys, 'chat.send')).toBe(true)
  })
})
