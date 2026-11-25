import i18n from '../i18n'

/**
 * LS-1: the register's copy arrives when the register is opened.
 *
 * The settings register carries 106 leaves that no other surface reads — the field hints
 * and the row titles of `settings.*`. They sat in the boot catalog, so every visitor
 * downloaded them (6.0 kB gzip of German, 5.3 kB of English) before opening a single
 * panel, and `de.js`/`en.js` crossed their ceilings doing it.
 *
 * `src/i18n.ts` already splits the catalog per language; this splits the register's half
 * of it per *visit*. The leaves live in `settingsCopy.<lang>.json` next to this module and
 * are merged into the same `translation` resource with `addResourceBundle`, so every key
 * path stays exactly as the register writes it: a hint leaf reads the same leaf it always
 * read, it is simply not in memory until somebody asks for it.
 *
 * The trigger sits in `src/pages/SettingsPage.tsx`, the route that opens the register, and
 * deliberately not inside `SettingsPanel`: that chunk holds 44.98 kB of its 45.0 kB
 * ceiling, so even the two lines of glue would have tipped it red.
 */

/** The language a request falls back to when its base has no copy of its own. */
const FALLBACK_LANGUAGE = 'en'

/** One language's register copy: the `settings` subtree, strings at the leaves. */
type SettingsCopy = { settings: Record<string, unknown> }

/**
 * Both languages named, so the bundler emits one lazy chunk per language and a German
 * visitor never fetches the English half. A computed specifier would hide both from it.
 */
const GERMAN = (): Promise<{ default: SettingsCopy }> => import('./settingsCopy.de.json')
const ENGLISH = (): Promise<{ default: SettingsCopy }> => import('./settingsCopy.en.json')

const loaders: Record<string, () => Promise<{ default: SettingsCopy }>> = {
  de: GERMAN,
  en: ENGLISH,
}

/** The copy for a locale tag's base language; a base without one gets the English half. */
function copyFor(wanted: string | undefined): {
  base: string
  read: () => Promise<{ default: SettingsCopy }>
} {
  const [base] = (wanted ?? '').split(/[-_]/)
  const read = base ? loaders[base] : undefined
  return read && base ? { base, read } : { base: FALLBACK_LANGUAGE, read: ENGLISH }
}

/** The language whose copy is in memory, and the read that put it there. */
let loadedFor: string | null = null
let pending: Promise<void> | null = null

/**
 * Merge the register copy for `language` (the running one by default) into the catalog.
 *
 * Repeat calls are free while the same language holds; a switch re-reads, because the
 * catalog `i18n.ts` bundled carries only the boot language's copy. A read that fails
 * leaves nothing marked, so the next opening of the register tries again — a register
 * painted without its hints is a worse outcome than one more request.
 */
export function ensureSettingsCopy(language?: string): Promise<void> {
  const { base, read } = copyFor(language ?? i18n.resolvedLanguage ?? i18n.language)
  if (loadedFor === base && pending) return pending
  const attempt: Promise<void> = read().then(
    (module) => {
      i18n.addResourceBundle(base, 'translation', module.default, true, true)
      loadedFor = base
    },
    (error: unknown) => {
      pending = null
      throw error
    },
  )
  pending = attempt
  return attempt
}

/** What is in memory right now — `null` before the first opening of the register. */
export function settingsCopyLanguage(): string | null {
  return loadedFor
}

/** Forget the loaded language; the next `ensureSettingsCopy` reads again. For tests. */
export function resetSettingsCopy(): void {
  loadedFor = null
  pending = null
}
