/**
 * KaTeX is fetched when a message first carries mathematics and never before.
 *
 * A static import here would repeat what `i18n.ts` does with the two locale
 * files: 270 kB of parser, layout and font metrics downloaded by every user for
 * something most sessions never touch. The promise is cached at module scope, so
 * ten formulas on one screen share one fetch, and this file is the only place the
 * package name appears.
 */
type KatexFactory = typeof import('katex').default

let pending: Promise<KatexFactory> | null = null

export function loadKatex(): Promise<KatexFactory> {
  if (!pending) {
    pending = Promise.all([
      import('katex'),
      // The stylesheet travels with the module it styles. Imported at the top of
      // the loader it would put KaTeX's rules and @font-face declarations into the
      // entry CSS.
      import('katex/dist/katex.min.css'),
    ])
      .then(([katex]) => katex.default)
      .catch((err: unknown) => {
        // A rejection stays uncached: one lost chunk request would otherwise leave
        // every later formula of the session dead.
        pending = null
        throw err
      })
  }
  return pending
}
