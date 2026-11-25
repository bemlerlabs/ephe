/**
 * An `export` on a name nothing imports is a promise the tree does not keep.
 *
 * TypeScript cannot help here: `noUnusedLocals` looks inside a file, and an exported name is
 * never unused inside its own file. So an `export` that no other file ever reads survives forever
 * and reads like an API. Measured over every tracked file on 2026-11-17 — 3610 paths, sources,
 * tests, docs, locales, Rust and JSON included — 32 exported `const`/`function`/`class` names in
 * `app/src` are named nowhere but their own declaration line. Seven of them sit in
 * `src/lib/api/marketplace.ts`: the client half of the market endpoints, with no page calling it.
 *
 * Deleting them is a product call, so this file holds the list instead of making it. The rule is
 * one-directional: a new exported name that no other file reads fails here, and a name on the list
 * that has been wired up or deleted fails here too, so the census cannot quietly rot.
 *
 * The census file itself quotes every name it lists, so it is exempt from its own corpus: it is
 * the one file that names the dead ones on purpose. It found that exemption by going red the
 * moment it was committed.
 *
 * What the rule can be fooled by, and whether it is: a symbol reached through a computed member
 * would look unused. `window[`, `globalThis[` and `eval(` do not appear anywhere in `app/src`, and
 * the only template `import(` is `./locales/${language}.json`, which loads a file, not a symbol.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const SRC_DIR = 'app/src/'

const SELF = path
  .relative(ROOT, fileURLToPath(import.meta.url))
  .split(path.sep)
  .join('/')

/** Declaration forms this census reads. Types and interfaces are excluded: they exist to be read
 *  across files and their absence from an import list means nothing. */
const DECLARATION = /^export\s+(?:async\s+)?(?:const|let|function|class)\s+([A-Za-z_$][\w$]*)/gm

/** Extensions a reference could hide in, everything tracked that a person or a build writes. */
const TEXT_SUFFIXES = new Set([
  '.ts',
  '.tsx',
  '.js',
  '.mjs',
  '.cjs',
  '.json',
  '.md',
  '.rs',
  '.py',
  '.html',
  '.css',
  '.yml',
  '.yaml',
  '.toml',
  '.txt',
  '.sh',
])

const TOKEN = /[A-Za-z_$][\w$]*/g

/**
 * Every name the census found that no other file reads, as `path#name` mapped to the line that
 * declares it. Lowering this list is the good direction: it means a name was wired into a page or
 * taken out of the tree.
 */
const UNIMPORTED: Record<string, string> = {
  'app/src/components/dashboard/ActivityFeed.tsx#AgentActivityRows':
    'export function AgentActivityRows({ activities }: { activities?: Activity[] })',
  'app/src/components/dashboard/chat/accessProfiles.ts#isAccessProfile':
    'export function isAccessProfile(value: string): value is AccessProfile {',
  'app/src/components/dashboard/chat/composerModelEntries.ts#entryMatchesQuery':
    'export function entryMatchesQuery(e: ModelChipEntry, query: string): boolean {',
  'app/src/components/dashboard/sidebarActionGroups.ts#tierOfEntry':
    'export function tierOfEntry(id: SidebarActionEntryId): string {',
  'app/src/components/model/modelPickerStore.ts#isFavorite':
    'export function isFavorite(id: string, favorites: string[]): boolean {',
  'app/src/components/model/modelPickerTypes.ts#rowsFromDetected':
    'export function rowsFromDetected(engine: DetectedEngine, group: string): Model',
  'app/src/components/model/modelPickerTypes.ts#rowsFromOptions':
    'export function rowsFromOptions(options: ModelOption[], group: string): ModelR',
  'app/src/components/onboarding/FirstRunIntro.tsx#BEAT_MS': 'export const BEAT_MS = 600',
  'app/src/components/onboarding/FirstRunIntro.tsx#CONDENSE_MS': 'export const CONDENSE_MS = 240',
  'app/src/lib/api/agents.ts#getAgent':
    'export function getAgent(id: string): Promise<AgentRecord> {',
  'app/src/lib/api/marketplace.ts#getMarketHome':
    'export function getMarketHome(): Promise<MarketHome> {',
  'app/src/lib/api/marketplace.ts#getMarketIndex':
    'export function getMarketIndex(): Promise<MarketIndexResponse> {',
  'app/src/lib/api/marketplace.ts#getMarketSources':
    'export function getMarketSources(): Promise<{',
  'app/src/lib/api/marketplace.ts#getMarketUpdates':
    'export function getMarketUpdates(): Promise<{',
  'app/src/lib/api/marketplace.ts#marketIconUrl':
    'export function marketIconUrl(name: string): string {',
  'app/src/lib/api/marketplace.ts#rollbackMarketPlugin':
    'export function rollbackMarketPlugin(name: string): Promise<MarketInstallResul',
  'app/src/lib/api/marketplace.ts#switchMarketPlugin': 'export function switchMarketPlugin(body: {',
  'app/src/lib/api/usage.ts#getToolUsage':
    'export function getToolUsage(top = 12): Promise<ToolUsageView> {',
  'app/src/lib/db.ts#dbDeleteCheckpoints':
    'export async function dbDeleteCheckpoints(sessionId: string): Promise<void> {',
  'app/src/lib/db.ts#dbGetSessionFolders':
    'export async function dbGetSessionFolders(): Promise<SessionFolder[]> {',
  'app/src/lib/db.ts#dbSetSessionFolders':
    'export async function dbSetSessionFolders(folders: SessionFolder[]): Promise<v',
  'app/src/lib/fileFormats.ts#isImage':
    "export function isImage(name: string, kind = ''): boolean {",
  'app/src/lib/firstRunTour.ts#TOUR_QUESTION_COUNT': 'export const TOUR_QUESTION_COUNT = 4',
  'app/src/lib/globalShortcut.ts#GLOBAL_SHORTCUT_KEYS':
    "export const GLOBAL_SHORTCUT_KEYS = ['mod', 'shift', 'e'] as const",
  'app/src/lib/modelFilter.ts#isNonChatModel':
    'export function isNonChatModel(model: string | undefined | null): boolean {',
  'app/src/lib/settingsIntent.ts#pendingSettingsIntent':
    'export function pendingSettingsIntent(): SettingsIntent | null {',
  'app/src/lib/shortcutDispatch.ts#registeredShortcutIds':
    'export function registeredShortcutIds(): string[] {',
  'app/src/lib/useMemoryFacts.ts#MEMORY_TYPES':
    "export const MEMORY_TYPES = ['semantic', 'episodic', 'procedural'] as const",
  'app/src/lib/useMemoryFacts.ts#memorySourceOf':
    'export function memorySourceOf(row: MemoryRow): string {',
  'app/src/lib/useUpdateCheck.ts#updateInfoOf':
    'export function updateInfoOf(answer: UpdateState): UpdateCheckInfo | null {',
  'app/src/lib/utils.ts#formatMessage': 'export function formatMessage(content: string): string {',
}

function trackedFiles(): string[] {
  const out = execFileSync('git', ['ls-files', '-z'], { cwd: ROOT, encoding: 'utf8' })
  return out.split('\0').filter((f) => f.length > 0 && !f.startsWith('.agents/'))
}

function readTracked(files: string[]): Map<string, string> {
  const corpus = new Map<string, string>()
  for (const rel of files) {
    const dot = rel.lastIndexOf('.')
    if (dot < 0 || !TEXT_SUFFIXES.has(rel.slice(dot).toLowerCase())) continue
    if (rel === SELF) continue
    try {
      corpus.set(rel, readFileSync(path.join(ROOT, rel), 'utf8'))
    } catch {
      // A tracked path that cannot be read is not evidence about a symbol; the scan continues.
    }
  }
  return corpus
}

function declarationSites(
  corpus: Map<string, string>,
): Map<string, { file: string; name: string; decl: string }> {
  const sites = new Map<string, { file: string; name: string; decl: string }>()
  for (const [rel, text] of corpus) {
    if (
      !rel.startsWith(SRC_DIR) ||
      !/\.tsx?$/.test(rel) ||
      rel.includes('.test.') ||
      rel.endsWith('.d.ts')
    )
      continue
    for (const match of text.matchAll(DECLARATION)) {
      const name = match[1]
      if (!name) continue
      const line = text.slice(match.index ?? 0).split('\n')[0] ?? ''
      sites.set(`${rel}#${name}`, { file: rel, name, decl: line.trim().slice(0, 78) })
    }
  }
  return sites
}

/**
 * The census as a pure function over a corpus, so the rule can be pinned without a filesystem.
 * A name counts as unimported when every occurrence of it sits in the file that declares it, and
 * there is exactly one occurrence: the declaration itself.
 */
export function unimportedNames(
  corpus: Map<string, string>,
  sites: Map<string, { file: string; name: string; decl: string }>,
): string[] {
  const wanted = new Set<string>()
  for (const site of sites.values()) wanted.add(site.name)
  const total = new Map<string, number>()
  const own = new Map<string, number>()
  for (const [rel, text] of corpus) {
    const tokens = text.match(TOKEN) ?? []
    for (const token of tokens) {
      if (!wanted.has(token)) continue
      total.set(token, (total.get(token) ?? 0) + 1)
      for (const key of sites.keys()) {
        const site = sites.get(key)
        if (site && site.name === token && site.file === rel) {
          const per = `${rel}#${token}`
          own.set(per, (own.get(per) ?? 0) + 1)
        }
      }
    }
  }
  const dead: string[] = []
  for (const [key, site] of sites) {
    if ((total.get(site.name) ?? 0) === 1 && (own.get(key) ?? 0) === 1) dead.push(key)
  }
  return dead.sort()
}

describe('the exports nobody imports', () => {
  const corpus = readTracked(trackedFiles())
  const sites = declarationSites(corpus)
  const found = unimportedNames(corpus, sites)

  it('holds no new name that no other file reads', () => {
    const grown = found.filter((key) => !(key in UNIMPORTED))
    expect(
      grown,
      `exported and unread elsewhere: ${grown.map((k) => `${k} (${sites.get(k)?.decl})`).join(', ')}`,
    ).toEqual([])
  })

  it('holds no name that has been wired up or taken away', () => {
    const shrunk = Object.keys(UNIMPORTED).filter((key) => !found.includes(key))
    expect(shrunk, `no longer on the census, so drop the line: ${shrunk.join(', ')}`).toEqual([])
  })

  it('skips exactly its own file, which quotes every name it lists', () => {
    expect(trackedFiles()).toContain(SELF)
    expect(corpus.has(SELF)).toBe(false)
  })

  it('reads a corpus it was handed, so the census is not decoration', () => {
    const planted = new Map<string, string>([
      ['app/src/a.ts', 'export const wired = 1\nexport const orphan = 2\n'],
      [
        'app/src/b.ts',
        'import { wired } from "./a"\nexport function usesWired(): number {\n  return wired\n}\n',
      ],
      ['app/src/c.ts', 'import { usesWired } from "./b"\nexport const value = usesWired()\n'],
      ['app/src/d.ts', 'import { value } from "./c"\nconst sum = value\nvoid sum\n'],
    ])
    const plantedSites = declarationSites(planted)
    expect(unimportedNames(planted, plantedSites)).toEqual(['app/src/a.ts#orphan'])
  })
})
