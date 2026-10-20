/**
 * W3-51: one row per setting, no orphans.
 *
 * The settings hub is two surfaces in one: the register fields (server payload,
 * rendered by DeepFields and found by matchFields) and the hand-built rows with
 * an endpoint of their own (rendered by the sections, indexed in ROW_INDEX,
 * found by matchRows). "One row per setting" is a statement about that index —
 * every entry stands for exactly one surface item, once. "No orphans" is
 * two-sided: no index entry points at nothing, and no hand-built row stands
 * outside the index where the search can never reach it.
 *
 * The row side is read as text (import.meta.glob ?raw, the style of
 * lib/i18n-keys.test.ts): a row title is a static `t('…')` literal in the
 * sections, so the surface the index must cover is a fixed set of keys.
 */
import { describe, it, expect } from 'vitest'
import i18next from 'i18next'

import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { NAV } from '../model'
import { ROW_INDEX } from './rowIndex'

const sections = import.meta.glob<string>(
  ['./sections-*.tsx', './approvalRegister.tsx', './AppearanceProfileSection.tsx'],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
)

// Every source outside the specs and the bundles — where an index key has to be
// built. The settings sections alone are not enough: the cron rows and the
// keep-awake row are rendered by SchedulerPanel / KeepAwakeToggle.
const sources = import.meta.glob<string>('../../../../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const TEST_FILE = /\.(test|spec)\.[tm]sx?$/

/**
 * Rows whose title names a state, not a setting: an empty list, a run that never
 * happened, a diagnosis. There is no value to persist, so there is nothing to
 * search for. Guarded below so the exemption cannot rot into covering a row that
 * no longer exists.
 */
const STATE_ROWS = new Set([
  'settings.hooksNoneTitle', // a live event without a single hook
  'settings.hooksRecentEmpty', // no hook has run yet
  'settings.codeExecReasonTitle', // the cell-integrity diagnosis
])

/** The i18n keys the sections render as a SettingsRow title. */
function rowTitleKeys(src: string): string[] {
  const keys: string[] = []
  const tag = /<(PageHeader|SettingsGroup|SettingsRow)\b/g
  for (const m of src.matchAll(/title=\{([^\n]*?)\}/g)) {
    const before = src.slice(0, m.index)
    const tags = [...before.matchAll(tag)]
    // The row title is the `title=` whose nearest enclosing element is a row —
    // a group heading or a page header does not name a setting.
    if (tags.at(-1)?.[1] !== 'SettingsRow') continue
    for (const k of (m[1] ?? '').matchAll(/(?<![A-Za-z0-9_$.])t\(\s*'([^']+)'/g)) {
      if (k[1]) keys.push(k[1])
    }
  }
  return keys
}

const titleKeys = Object.values(sections).flatMap(rowTitleKeys)
const allSource = Object.entries(sources)
  .filter(([p]) => !TEST_FILE.test(p))
  .map(([, raw]) => raw)
  .join('\n')

const labelIn = (lng: 'de' | 'en', key: string): string => {
  const i = i18next.createInstance()
  void i.init({
    resources: { de: { translation: de }, en: { translation: en } },
    lng,
    fallbackLng: lng,
    supportedLngs: [lng],
    interpolation: { escapeValue: false },
  })
  return i.t(key, { defaultValue: '' })
}

describe('W3-51 — eine Zeile pro Einstellung', () => {
  it('no key twice: no entry sits in the index twice', () => {
    const seen = new Set<string>()
    const dup = ROW_INDEX.map((e) => e.key).filter((k) =>
      seen.has(k) ? true : (seen.add(k), false),
    )
    expect(dup).toEqual([])
  })

  it('no (tab, key) pair twice', () => {
    const seen = new Set<string>()
    const dup = ROW_INDEX.map((e) => `${e.tab}:${e.key}`).filter((k) =>
      seen.has(k) ? true : (seen.add(k), false),
    )
    expect(dup).toEqual([])
  })

  it('every tab is a navigation tab: no row points at a place that does not exist', () => {
    const nav = new Set(NAV.map((n) => n.key))
    const foreign = ROW_INDEX.filter((e) => !nav.has(e.tab)).map((e) => `${e.tab}:${e.key}`)
    expect(foreign).toEqual([])
  })

  it('jeder Schluessel loest in beiden Sprachen zu einem Label auf', () => {
    const empty = ROW_INDEX.map((e) => e.key)
      .filter((k) => !labelIn('de', k) || !labelIn('en', k))
      .map((k) => k)
    expect(empty).toEqual([])
  })
})

describe('W3-51 — no orphan row: every hand-built row is in the index', () => {
  it('the three state rows are still there: the exemption does not point at nothing', () => {
    const gone = [...STATE_ROWS].filter((k) => !titleKeys.includes(k))
    expect(gone).toEqual([])
  })

  it('no SettingsRow title of the sections sits outside the index', () => {
    const indexed = new Set(ROW_INDEX.map((e) => e.key))
    const orphans = [...new Set(titleKeys)]
      .filter((k) => !indexed.has(k) && !STATE_ROWS.has(k))
      .map((k) => k)
    expect(orphans).toEqual([])
  })

  it('the same setting is not built as a row twice', () => {
    const count = new Map<string, number>()
    for (const k of titleKeys) count.set(k, (count.get(k) ?? 0) + 1)
    const twice = [...count].filter(([k, n]) => n > 1 && !STATE_ROWS.has(k)).map(([k]) => k)
    expect(twice).toEqual([])
  })
})

describe('W3-51 — no orphan index entry: every entry is built', () => {
  it('jeder Index-Schluessel kommt in den Quellen vor (oder sein Template-Familienzweig)', () => {
    // `t(\`settings.plugins.${seg}\`)` builds public/personal; the family prefix
    // before a `${` is the evidence that a family is still rendered.
    const dead = ROW_INDEX.filter((e) => {
      const family = `${e.key.slice(0, e.key.lastIndexOf('.') + 1)}`
      return !allSource.includes(e.key) && !allSource.includes(`${family}$` + '{')
    }).map((e) => `${e.tab}:${e.key}`)
    expect(dead).toEqual([])
  })
})
