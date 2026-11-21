// Ephe — import extraction for the architecture checker: code only, never prose.
//
// The checker builds its dependency graph from a regex over file text. Run over
// raw text, that regex also reads comments — and a comment that *mentions* a
// module path then becomes a dependency edge. Measured on 2026-10-08: a header
// comment in app/src/lib/api/artifacts.ts, reworded by the English sweep, wrapped
// onto a line starting `from '@/lib/api'.` and Tarjan reported a three-node cycle
// that does not exist. The gate went red on a sentence.
//
// So comments are blanked before matching. What is left is the same set of
// specifiers a real parser would find for this checker's purpose, and a comment
// in any language can no longer move the graph.
//
// Known limit, on purpose: a Python docstring is not a comment, so a docstring
// that spells `from 'x'` still reads as an edge. Stripping those needs an AST
// pass (see scripts/language_inventory.py, which does exactly that for prose);
// remaining a text filter is what keeps the checker fast enough for a commit hook.

const BLOCK_SLASH = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.rs']);
const LINE_HASH = new Set(['.py', '.sh', '.yaml', '.yml', '.toml']);

/** Blank block and line comments for the given file extension, keeping line count. */
export function stripComments(text, ext) {
  const block = BLOCK_SLASH.has(ext);
  const hash = LINE_HASH.has(ext);
  if (!block && !hash) return text;
  if (block) {
    // Keep the newlines: the checker counts lines elsewhere and a collapsed file
    // would move every finding's position for an unrelated reason.
    text = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ''));
  }
  return text
    .split('\n')
    .map((line) => (hash ? cutHash(line) : cutSlash(line)))
    .join('\n');
}

/** `#` starts a comment only at line start or after whitespace — `"a#b"` is not one. */
function cutHash(line) {
  for (let i = line.indexOf('#'); i >= 0; i = line.indexOf('#', i + 1)) {
    if (i === 0 || /\s/.test(line[i - 1])) return line.slice(0, i);
  }
  return line;
}

/** `//` starts a comment unless it is the `://` of a URL sitting in code. */
function cutSlash(line) {
  for (let i = line.indexOf('//'); i >= 0; i = line.indexOf('//', i + 2)) {
    if (line[i - 1] !== ':') return line.slice(0, i);
  }
  return line;
}

/** Every module specifier the file imports, from its code alone. */
export function importSpecifiers(text, ext) {
  const code = stripComments(text, ext);
  const specs = [];
  for (const m of code.matchAll(/(?:from|import)\s*['"]([^'"]+)['"]/g)) specs.push(m[1]);
  for (const m of code.matchAll(/require\(\s*['"]([^'"]+)['"]\s*\)/g)) specs.push(m[1]);
  return specs;
}
