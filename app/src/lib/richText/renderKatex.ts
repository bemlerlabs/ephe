import { loadKatex } from './loadKatex'

/**
 * Composes one formula to HTML.
 *
 * `throwOnError` is on because the caller reports a malformed formula as a
 * sentence; KaTeX's own fallback paints the raw source in red, which reads as a
 * styling choice rather than as a failure.
 *
 * The two guards that matter for hostile input are KaTeX's defaults, left alone:
 * `trust: false` drops `\href{javascript:…}` instead of emitting a live link, and
 * `maxExpand: 1000` ends a recursive `\def` chain before it can spin.
 */
export async function renderKatex(tex: string, display: boolean): Promise<string> {
  const katex = await loadKatex()
  return katex.renderToString(tex, { displayMode: display, throwOnError: true })
}
