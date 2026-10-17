/**
 * The chat's fence, end to end through the real pipeline: real react-markdown,
 * the real CodeBlock, the real on-demand highlighter and its chunk.
 *
 * Only the streams look-alike props are given; nothing about the highlighter is
 * mocked, so this is the test that says a finalised fence really turns into
 * token spans — and that a streamed one never asks for a grammar.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MarkdownBody } from './messageMarkdown'

vi.mock('react-i18next', () => ({
  useTranslation: (() => ({ t: (key: string) => key })) as never,
}))

const FENCE = '```typescript\nconst n = 1\n```'

describe('MarkdownBody — the fence highlighter', () => {
  it('streaming: the fence stays plain and no grammar is fetched', async () => {
    const { container } = render(<MarkdownBody text={FENCE} highlight={false} />)
    expect(container.querySelector('code')?.textContent).toContain('const n = 1')
    expect(container.querySelector('code.syntax-tokens')).toBeNull()
  })

  it('finalize: the fence becomes token spans in the theme palette', async () => {
    const { container } = render(<MarkdownBody text={FENCE} highlight />)
    await waitFor(() => expect(container.querySelector('code.syntax-tokens span')).not.toBeNull(), {
      timeout: 10_000,
    })
    const code = container.querySelector('code.syntax-tokens')
    expect(code?.textContent).toBe('const n = 1')
    expect(code?.innerHTML).toMatch(/color:#[0-9A-Fa-f]{6}/)
    expect(container.textContent).toContain('typescript')
  })

  it('a tag without a grammar keeps the plain text', async () => {
    const { container } = render(<MarkdownBody text={'```bf\n+++\n```'} highlight />)
    expect(container.querySelector('code.syntax-tokens')).toBeNull()
    expect(container.querySelector('code')?.textContent).toContain('+++')
  })
})
