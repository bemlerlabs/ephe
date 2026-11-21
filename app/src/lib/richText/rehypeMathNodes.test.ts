/**
 * The three corrections `rehypeMathNodes` makes to remark-math's output, checked on
 * the tree shapes remark-math actually produces.
 *
 * The trees here are hand-built because they carry positions, and the positions are
 * the point: a surface restored from the vfile has to come back byte for byte.
 */
import { describe, it, expect } from 'vitest'
import { rehypeMathNodes, BLOCK_TAG, INLINE_TAG } from './rehypeMathNodes'

interface Position {
  start: { offset: number }
  end: { offset: number }
}
interface Node {
  type: string
  tagName?: string
  value?: string
  properties?: { className?: unknown }
  children?: Node[]
  position?: Position
}

function text(value: string): Node {
  return { type: 'text', value }
}

function mathCode(kind: string, value: string, span?: [number, number]): Node {
  return {
    type: 'element',
    tagName: 'code',
    properties: { className: ['language-math', kind] },
    children: [text(value)],
    ...(span ? { position: { start: { offset: span[0] }, end: { offset: span[1] } } } : {}),
  }
}

function paragraphOf(children: Node[]): Node {
  return { type: 'element', tagName: 'p', children }
}

function at<T>(items: T[] | undefined, index: number): T {
  const found = items?.[index]
  if (found === undefined) throw new Error(`no node at ${index}`)
  return found
}

/** Runs the plugin over one paragraph and hands back its rewritten children. */
function inside(children: Node[], source = ''): Node[] {
  const root: Node = { type: 'root', children: [paragraphOf(children)] }
  rehypeMathNodes()(root as never, { value: source })
  return at(root.children, 0).children ?? []
}

describe('rehypeMathNodes', () => {
  it('reads the display intent of `$$…$$` off the source, not the node kind', () => {
    const source = '$$\\int_0^1 x\\,dx$$'
    const formula = at(
      inside([mathCode('math-inline', '\\int_0^1 x\\,dx', [0, source.length])], source),
      0,
    )
    expect(formula.tagName).toBe(BLOCK_TAG)
    expect(at(formula.children, 0).value).toBe('\\int_0^1 x\\,dx')
  })

  it('unwraps the block form that arrives inside a pre', () => {
    const root: Node = {
      type: 'root',
      children: [{ type: 'element', tagName: 'pre', children: [mathCode('math-display', 'x')] }],
    }
    rehypeMathNodes()(root as never, { value: '$$\nx\n$$' })
    const block = at(root.children, 0)
    expect(block.tagName).toBe(BLOCK_TAG)
    expect(at(block.children, 0).value).toBe('x')
  })

  it('puts a price list back exactly as the reader wrote it', () => {
    const source = 'the licence is $5 and the add-on $12'
    const nodes = inside(
      [text('the licence is '), mathCode('math-inline', '5 and the add-on ', [15, 34]), text('12')],
      source,
    )
    expect(nodes.map((node) => node.value ?? '').join('')).toBe(source)
    expect(nodes.some((node) => node.tagName)).toBe(false)
  })

  it('rejects a single-dollar pair whose body touches the delimiters', () => {
    const source = '$  z  $'
    expect(at(inside([mathCode('math-inline', ' z ', [0, source.length])], source), 0)).toEqual({
      type: 'text',
      value: source,
    })
  })

  it('keeps a single-dollar pair that reads as a formula', () => {
    const source = '$x + y$'
    expect(
      at(inside([mathCode('math-inline', 'x + y', [0, source.length])], source), 0).tagName,
    ).toBe(INLINE_TAG)
  })

  it('leaves a fence alone, whatever it contains', () => {
    const fenced: Node = {
      type: 'element',
      tagName: 'pre',
      children: [
        {
          type: 'element',
          tagName: 'code',
          properties: { className: ['language-mermaid'] },
          children: [text('graph TD; A-->B\n')],
        },
      ],
    }
    const root: Node = { type: 'root', children: [fenced] }
    rehypeMathNodes()(root as never, { value: '```mermaid\ngraph TD; A-->B\n```' })
    expect(root.children).toEqual([fenced])
  })

  it('falls back to inline when no source came along', () => {
    expect(at(inside([mathCode('math-inline', 'x')]), 0).tagName).toBe(INLINE_TAG)
  })

  it('rebuilds the delimiters when a rejected pair has no source', () => {
    expect(at(inside([mathCode('math-inline', '5 and the add-on ')]), 0).value).toBe(
      '$5 and the add-on $',
    )
  })
})
