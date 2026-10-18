import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

/**
 * WD-33: the language the user reads, and only that one.
 *
 * Both catalogs were static imports, so every user downloaded English *and* German
 * (~186 KB) before the first paint while reading one of them. Each catalog is a chunk of
 * its own now: `storedLanguage()` decides which one the first render needs, the `await`
 * below is the readiness gate that replaced the static imports, and the other file is
 * fetched only when somebody switches to it.
 *
 * No flash of untranslated keys, in both directions:
 *  - the first paint waits for the active catalog (nothing renders before this module
 *    resolves — `main.tsx` imports it for exactly that reason);
 *  - on a switch, i18next reads through `catalogBackend` *before* it emits
 *    `languageChanged`, so German is painted with German already in memory.
 *
 * A switch whose chunk never arrives is not covered by that: i18next announces a language
 * even when the backend reported an error for it, so the announcement stands with no
 * catalog behind it and that language paints key paths. Closing the gap means promising
 * that the language the user was reading stays, a retention promise this module does not
 * make; `src/i18n.lazySplit.test.ts` measures the shape instead.
 */
const SUPPORTED_LANGUAGES = ['en', 'de'] as const
type Language = (typeof SUPPORTED_LANGUAGES)[number]

/** The language a user with no stored choice reads — the same default as `fallbackLng`. */
const FALLBACK_LANGUAGE: Language = 'en'

/** The key `i18next-browser-languagedetector` below reads and writes. */
const LANGUAGE_STORAGE_KEY = 'i18nextLng'

/** A catalog as JSON hands it over: nested objects, strings at the leaves. */
type TranslationCatalog = Record<string, unknown>

/** `de`, `de-DE` and `de_DE` name one language; the detector and i18next both say so. */
const baseLanguage = (value: string | null | undefined): string => value?.split(/[-_]/)[0] ?? ''

const isLanguage = (value: string): value is Language =>
  (SUPPORTED_LANGUAGES as readonly string[]).includes(value)

/**
 * The detector's own localStorage rule, decided before `init` so that the preloaded
 * catalog is always the catalog the detected language needs. An unsupported value — or a
 * storage that refuses to be read, as in a locked-down webview — falls back to English
 * exactly as the detector would.
 */
export function languageFrom(stored: string | null, browser: string): Language {
  const base = baseLanguage(stored)
  if (isLanguage(base)) return base
  // A first start has no stored choice yet. The browser's own language is the
  // person's answer then; an unsupported stored value still falls back to English.
  if (!stored) {
    const browserBase = baseLanguage(browser)
    if (isLanguage(browserBase)) return browserBase
  }
  return FALLBACK_LANGUAGE
}

function storedLanguage(): Language {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
  } catch {
    stored = null
  }
  return languageFrom(stored, typeof navigator !== 'undefined' ? navigator.language : '')
}

/** One chunk per language: this call is what keeps a catalog out of the entry chunk. */
const loadCatalog = (language: Language) =>
  import(`./locales/${language}.json`) as Promise<{ default: TranslationCatalog }>

/** The language this module booted with — decided once, before i18next is told anything. */
const activeLanguage = storedLanguage()

/**
 * The language a running switch is heading to. `languageChanging` is emitted before
 * i18next resolves that language and reads its namespace, and it carries the raw choice;
 * the fallback language of that switch is not it.
 */
let switchingTo: string | null = null
i18n.on('languageChanging', (language: string) => {
  switchingTo = baseLanguage(language)
})

/**
 * What i18next reads for a language it does not hold in memory yet. Two reads are
 * answered, both of them the user's own choice: the language this module booted with
 * (the retry path for a preload that came back empty) and the language a switch is
 * heading to. Every other read is a fallback read — English as the backdrop of a German
 * session, which is exactly the byte this split exists to not download — and it is told
 * the namespace is loaded while carrying nothing.
 *
 * The price of that answer is the cross-language net: a key missing from the active
 * catalog reads as its own key path instead of as English. `completeness.test.ts` is the
 * gate that keeps every key present in both files, so the net only shows up on a defect.
 */
const catalogBackend = {
  type: 'backend' as const,
  init() {},
  read(
    language: string,
    _namespace: string,
    callback: (error: unknown, catalog?: TranslationCatalog) => void,
  ) {
    const base = baseLanguage(language)
    const chosen = base === switchingTo || base === activeLanguage
    if (!isLanguage(base) || !chosen) {
      callback(null, undefined)
      return
    }
    loadCatalog(base).then(
      (module) => callback(null, module.default),
      (error) => callback(error, undefined),
    )
  },
}

// A catalog that will not load must not take the app down: the backend above reads this
// language as well when it was not bundled, and if that read fails too the worst case is a
// first paint of key paths instead of nothing. No retry loop follows the failure — i18next
// re-reads only a read that came back with data (`err && data` in its own `read`), and this
// backend hands back no catalog beside its error.
const activeCatalog = await loadCatalog(activeLanguage)
  .then((module) => module.default)
  .catch(() => null)

await i18n
  .use(LanguageDetector)
  .use(catalogBackend)
  .use(initReactI18next)
  .init({
    // Only the active language is bundled at init; `partialBundledLanguages` is what
    // sends every other language through `catalogBackend` instead of answering from this
    // object alone.
    resources: activeCatalog ? { [activeLanguage]: { translation: activeCatalog } } : {},
    // The boot language is the fallback too: with no stored choice it is the
    // browser's language, and the only catalog bundled at init is its own — a
    // fallback of `en` beside a bundled `de` left every key path raw (measured on
    // the fresh first open, 2026-10-17).
    fallbackLng: activeLanguage,
    supportedLngs: [...SUPPORTED_LANGUAGES],
    load: 'languageOnly',
    partialBundledLanguages: true,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      // A stored choice wins; without one the boot language above is the answer.
      order: ['localStorage'],
      caches: ['localStorage'],
    },
  })

// R36: let <html lang> follow the language the UI is actually in — the value
// hardcoded in index.html cannot express the user's choice, and screen readers
// would otherwise announce the interface with the wrong pronunciation rules.
const syncDocumentLang = (lng: string) => {
  document.documentElement.lang = lng || 'en'
}
i18n.on('languageChanged', syncDocumentLang)
syncDocumentLang(i18n.language)

export default i18n
