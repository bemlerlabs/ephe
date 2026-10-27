/**
 * The fence's on-demand highlighter at its call site.
 *
 * A streaming message renders the plain text and asks for nothing; a finalised
 * one asks for the grammar of its tag and swaps the tokens in when they arrive.
 * A tag without a grammar, or a chunk that did not come back, leaves the plain
 * text on screen — the fence has to stay readable either way.
 */
import { createElement } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import CodeBlock from '@/components/dashboard/CodeBlock'

const { highlightFence, copyTyped } = vi.hoisted(() => ({
  highlightFence: vi.fn(),
  copyTyped: vi.fn(async () => true),
}))
vi.mock('@/lib/syntaxHighlighter', () => ({ highlightFence }))
vi.mock('@/lib/clipboard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/clipboard')>()
  return { ...actual, copyTypedText: copyTyped }
})
vi.mock('react-i18next', () => ({
  useTranslation: (() => ({ t: (key: string) => key })) as never,
}))

const SOURCE = 'const n = 1'
const TOKENS = '<span style="color:#FF7B72">const</span><span> n = 1</span>'

/** What ReactMarkdown's `pre` renderer hands CodeBlock: the inner <code>. */
const fence = () => createElement('code', { className: 'language-ts' }, SOURCE)

beforeEach(() => {
  highlightFence.mockReset()
  copyTyped.mockClear()
})

describe('CodeBlock — the copy button', () => {
  it('hands the fence to the typed clipboard, plain and HTML', async () => {
    render(<CodeBlock>{fence()}</CodeBlock>)

    fireEvent.click(screen.getByLabelText('codeBlock.copy'))

    await waitFor(() =>
      expect(copyTyped).toHaveBeenCalledWith(
        SOURCE,
        '<pre><code class="language-ts">const n = 1</code></pre>',
      ),
    )
    expect(await screen.findByLabelText('codeBlock.copied')).toBeTruthy()
  })
})

describe('CodeBlock — the on-demand highlighter', () => {
  it('streaming: renders the plain text and asks the highlighter for nothing', () => {
    const { container } = render(<CodeBlock>{fence()}</CodeBlock>)
    expect(highlightFence).not.toHaveBeenCalled()
    expect(container.querySelector('code')?.textContent).toBe(SOURCE)
    expect(container.querySelector('code')?.className).not.toContain('syntax-tokens')
  })

  it('finalize: asks for the fence tag and swaps the token spans in', async () => {
    highlightFence.mockResolvedValue(TOKENS)
    const { container } = render(<CodeBlock highlight>{fence()}</CodeBlock>)
    expect(highlightFence).toHaveBeenCalledWith(SOURCE, 'ts')
    await waitFor(() => expect(container.querySelector('code span')).not.toBeNull())
    const code = container.querySelector('code')
    expect(code?.className).toContain('syntax-tokens')
    expect(code?.className).toContain('language-ts')
    expect(code?.innerHTML).toBe(TOKENS)
  })

  it('a tag without a grammar keeps the plain text (the highlighter answers null)', async () => {
    highlightFence.mockResolvedValue(null)
    const { container } = render(<CodeBlock highlight>{fence()}</CodeBlock>)
    await waitFor(() => expect(highlightFence).toHaveBeenCalled())
    expect(container.querySelector('code')?.textContent).toBe(SOURCE)
    expect(container.querySelector('code')?.className).not.toContain('syntax-tokens')
  })

  it('copy takes the source text, not the swapped-in token DOM', async () => {
    highlightFence.mockResolvedValue(TOKENS)
    const { container } = render(<CodeBlock highlight>{fence()}</CodeBlock>)
    await waitFor(() => expect(container.querySelector('code span')).not.toBeNull())
    screen.getByRole('button').click()
    await waitFor(() => expect(copyTyped).toHaveBeenCalledWith(SOURCE, expect.any(String)))
  })

  it('the direct-code path (no Markdown AST) highlights nothing on its own', () => {
    const { container } = render(<CodeBlock code={SOURCE} language="typescript" />)
    expect(highlightFence).not.toHaveBeenCalled()
    expect(container.querySelector('code')?.className).toContain('hljs')
    expect(container.querySelector('code')?.className).toContain('language-typescript')
  })
})
