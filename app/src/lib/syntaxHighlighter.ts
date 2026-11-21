/**
 * The highlighter a code fence pulls in on demand.
 *
 * The grammar set is the heaviest dependency this bundle can reach, and a fence
 * needs it only once the message around it is final. The chat renders the plain
 * text first and swaps the colours in when the chunk has landed, so a streaming
 * message never waits for a grammar.
 *
 * Every language is its own chunk: the first fence downloads core, engine, theme
 * and its one grammar, plus whatever that grammar embeds (the PHP grammar reads
 * HTML and JavaScript). A tag the table below does not name keeps the plain
 * rendering, as a fence outside the previous highlighter's common set did.
 *
 * Ruby and C++ are the two languages left out on purpose: the Ruby grammar
 * imports the C++ one, whose 501 kB chunk would be the only chunk across
 * vite.config's 500 kB warning line.
 *
 * The WebAssembly engine stays out. The JavaScript engine reads the same
 * grammars and adds no binary fetch to the first fence.
 */
import type { LanguageInput } from 'shiki/core'

type GrammarChunk = () => Promise<{ default: LanguageInput }>

/** Grammar name -> its chunk. */
const GRAMMARS: Record<string, GrammarChunk> = {
  c: () => import('shiki/langs/c.mjs'),
  csharp: () => import('shiki/langs/csharp.mjs'),
  css: () => import('shiki/langs/css.mjs'),
  diff: () => import('shiki/langs/diff.mjs'),
  dockerfile: () => import('shiki/langs/dockerfile.mjs'),
  go: () => import('shiki/langs/go.mjs'),
  graphql: () => import('shiki/langs/graphql.mjs'),
  html: () => import('shiki/langs/html.mjs'),
  ini: () => import('shiki/langs/ini.mjs'),
  java: () => import('shiki/langs/java.mjs'),
  javascript: () => import('shiki/langs/javascript.mjs'),
  json: () => import('shiki/langs/json.mjs'),
  jsx: () => import('shiki/langs/jsx.mjs'),
  kotlin: () => import('shiki/langs/kotlin.mjs'),
  less: () => import('shiki/langs/less.mjs'),
  lua: () => import('shiki/langs/lua.mjs'),
  makefile: () => import('shiki/langs/makefile.mjs'),
  markdown: () => import('shiki/langs/markdown.mjs'),
  objectivec: () => import('shiki/langs/objective-c.mjs'),
  perl: () => import('shiki/langs/perl.mjs'),
  php: () => import('shiki/langs/php.mjs'),
  python: () => import('shiki/langs/python.mjs'),
  r: () => import('shiki/langs/r.mjs'),
  rust: () => import('shiki/langs/rust.mjs'),
  scss: () => import('shiki/langs/scss.mjs'),
  shellscript: () => import('shiki/langs/shellscript.mjs'),
  sql: () => import('shiki/langs/sql.mjs'),
  swift: () => import('shiki/langs/swift.mjs'),
  toml: () => import('shiki/langs/toml.mjs'),
  tsx: () => import('shiki/langs/tsx.mjs'),
  typescript: () => import('shiki/langs/typescript.mjs'),
  xml: () => import('shiki/langs/xml.mjs'),
  yaml: () => import('shiki/langs/yaml.mjs'),
}

/** The spellings a fence writes that do not equal the grammar name above. These
 *  are tags someone actually types; every other shorthand stays plain. */
const SPELLINGS: Record<string, string> = {
  bash: 'shellscript',
  cjs: 'javascript',
  console: 'shellscript',
  cs: 'csharp',
  golang: 'go',
  htm: 'html',
  jsonc: 'json',
  kt: 'kotlin',
  md: 'markdown',
  mjs: 'javascript',
  patch: 'diff',
  py: 'python',
  rs: 'rust',
  sh: 'shellscript',
  ts: 'typescript',
  yml: 'yaml',
  zsh: 'shellscript',
}

/** The palette `app/src/styles/highlight.css` paints for the hljs path, so a
 *  fence does not change colour with the highlighter behind it. */
const THEME = 'github-dark-default'

type Highlighter = Awaited<ReturnType<typeof build>>

let pending: Promise<Highlighter | null> | null = null

async function build() {
  const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] = await Promise.all([
    import('shiki/core'),
    import('shiki/engine/javascript'),
  ])
  return createHighlighterCore({
    themes: [import('shiki/themes/github-dark-default.mjs')],
    langs: [],
    engine: createJavaScriptRegexEngine(),
  })
}

/**
 * Core, engine and theme, fetched once per session. A failed fetch clears the
 * slot, so a fence after a network hiccup tries again instead of leaving the
 * session without colours.
 */
function highlighter() {
  if (!pending) {
    pending = build().catch(() => {
      pending = null
      return null
    })
  }
  return pending
}

/**
 * The token spans for one fence, or null when there is nothing to colour — an
 * unknown tag, a chunk that did not arrive, a grammar that refused the input.
 * A null answer leaves the caller with the plain text it already rendered.
 */
export async function highlightFence(code: string, tag: string): Promise<string | null> {
  const name = GRAMMARS[tag] ? tag : SPELLINGS[tag]
  if (!name) return null
  const chunk = GRAMMARS[name]
  if (!chunk || !code.trim()) return null
  try {
    const shiki = await highlighter()
    if (!shiki) return null
    if (!shiki.getLoadedLanguages().includes(name)) {
      const grammar = await chunk()
      await shiki.loadLanguage(grammar.default)
    }
    return shiki.codeToHtml(code, { lang: name, theme: THEME, structure: 'inline' })
  } catch {
    return null
  }
}
