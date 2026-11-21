/**
 * Maps the math elements `remark-math` produces onto the two components the
 * bubble renders.
 *
 * The delimiters themselves belong to remark-math: it tokenizes `$…$` and `$$…$$`
 * before Markdown's escape rules run, which is the only reason `\{`, `\%` and `\\`
 * reach the renderer intact. Three of its decisions are corrected here.
 *
 *   1. `$$…$$` written on one line arrives as *inline* math. The source it came
 *      from starts with `$$`, and that delimiter decides the display form.
 *   2. `$5 and the add-on $12` arrives as a formula. A single-dollar pair whose
 *      body starts or ends with whitespace, or that is nothing but a number, goes
 *      back as the text it was.
 *   3. The block form (`$$` on its own line) arrives as `pre > code` and needs the
 *      code wrapper taken off.
 *
 * The vfile is what makes 1 and 2 exact: the position of an element indexes the
 * Markdown the reader sent, so a rejected pair is restored byte for byte instead of
 * being rebuilt from its parts.
 */

interface Position {
  start: { offset?: number }
  end: { offset?: number }
}
interface Node {
  type: string
  tagName?: string
  value?: string
  properties?: { className?: unknown }
  children?: Node[]
  position?: Position
}
interface Parent {
  children?: Node[]
}
interface VFileLike {
  value?: unknown
}

export const INLINE_TAG = 'math-inline'
export const BLOCK_TAG = 'math-block'

const MATH_CLASS = 'language-math'
const DISPLAY_CLASS = 'math-display'
const INLINE_CLASS = 'math-inline'
const PURE_NUMBER = /^[\d.,:\s]+$/

function classes(node: Node): string[] {
  const raw = node.properties?.className
  if (Array.isArray(raw)) return raw.filter((name): name is string => typeof name === 'string')
  return typeof raw === 'string' ? [raw] : []
}

function isMath(node: Node | undefined, kind: string): boolean {
  const names = node ? classes(node) : []
  return (
    node?.type === 'element' &&
    node.tagName === 'code' &&
    names.includes(MATH_CLASS) &&
    names.includes(kind)
  )
}

function textOf(node: Node): string {
  if (node.type === 'text') return node.value ?? ''
  return (node.children ?? []).map(textOf).join('')
}

/** The exact Markdown an element was parsed from, when the position allows it. */
function sourceOf(node: Node, source: string): string | null {
  const start = node.position?.start?.offset
  const end = node.position?.end?.offset
  if (!source || typeof start !== 'number' || typeof end !== 'number' || end <= start) return null
  return source.slice(start, end)
}

function formula(tex: string): boolean {
  const body = tex.trim()
  return body.length > 0 && body === tex && !PURE_NUMBER.test(tex)
}

function mathElement(tagName: string, tex: string): Node {
  // `properties` is required: react-markdown's element walk reads it before it ever
  // reaches the component.
  return { type: 'element', tagName, properties: {}, children: [{ type: 'text', value: tex }] }
}

function rewrite(parent: Parent, source: string): void {
  const next: Node[] = []
  for (const child of parent.children ?? []) {
    if (child.type === 'element' && child.tagName === 'pre') {
      const inner = (child.children ?? []).filter(
        (node) => node.type === 'element' || (node.type === 'text' && !!node.value?.trim()),
      )
      const [only] = inner
      if (inner.length === 1 && only && isMath(only, DISPLAY_CLASS)) {
        next.push(mathElement(BLOCK_TAG, textOf(only)))
        continue
      }
    }
    if (isMath(child, DISPLAY_CLASS)) {
      next.push(mathElement(BLOCK_TAG, textOf(child)))
      continue
    }
    if (isMath(child, INLINE_CLASS)) {
      const tex = textOf(child)
      const exact = sourceOf(child, source)
      if (exact?.startsWith('$$')) {
        next.push(mathElement(BLOCK_TAG, tex))
      } else if (formula(tex)) {
        next.push(mathElement(INLINE_TAG, tex))
      } else {
        next.push({ type: 'text', value: exact ?? `$${tex}$` })
      }
      continue
    }
    if (child.type === 'element' && !classes(child).includes(MATH_CLASS)) {
      rewrite(child, source)
    }
    next.push(child)
  }
  parent.children = next
}

export function rehypeMathNodes() {
  // react-markdown hands every rehype transformer the vfile it parsed, so the
  // plugin stays a module constant while still reading the text of one message.
  return (tree: Parent, file?: VFileLike): void => {
    const source = typeof file?.value === 'string' ? file.value : ''
    rewrite(tree, source)
  }
}
