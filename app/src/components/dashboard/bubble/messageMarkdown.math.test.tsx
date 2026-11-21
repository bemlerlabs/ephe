/**
 * The seam the engine's output goes through: one assistant message carrying
 * `$…$`, `$$…$$` and a ```mermaid fence, parsed by the real Markdown pipeline.
 *
 * mermaid is mocked for the drawing itself, so the assertions are about the wiring —
 * fence to renderer, formula to KaTeX, and a rejected diagram to a sentence with the
 * rest of the message still standing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import mermaid from 'mermaid'
import { MarkdownBody, UserMarkdown } from './messageMarkdown'

vi.mock('mermaid', () => ({
  default: { initialize: vi.fn(), render: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const draw = mermaid.render as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  draw.mockReset()
  draw.mockResolvedValue({ svg: '<svg data-testid="diagram"></svg>' })
})

const body = (text: string) => render(<MarkdownBody text={text} highlight={false} />)

describe('mathematics in a message', () => {
  it('sets an inline formula without disturbing the sentence around it', async () => {
    const { container } = body('The area is $\\pi r^2$ exactly.')
    await waitFor(() => expect(container.querySelector('.katex')).toBeTruthy())
    expect(container.textContent).toContain('The area is')
    expect(container.textContent).toContain('exactly.')
    expect(container.textContent).toContain('π')
  })

  it('gives a `$$…$$` formula written on one line the display form', async () => {
    const { container } = body('$$E = mc^2$$')
    await waitFor(() => expect(container.querySelector('.katex-display')).toBeTruthy())
  })

  it('keeps a formula its own line when the engine writes the block form', async () => {
    const { container } = body('$$\n\\int_0^1 x\\,dx\n$$')
    await waitFor(() => expect(container.querySelector('.katex-display')).toBeTruthy())
  })

  it('keeps the backslashes a formula needs', async () => {
    const { container } = body('A set $\\{x : x > 0\\}$ and fifty percent is 50\\%.')
    await waitFor(() => expect(container.querySelector('.katex')).toBeTruthy())
    expect(container.textContent).toContain('{')
    expect(container.textContent).toContain('>')
    expect(container.textContent).toContain('50%')
  })

  it('leaves a price list as prose', async () => {
    const { container } = body('The licence is $5 and the add-on $12.')
    await waitFor(() => expect(container.querySelector('p')).toBeTruthy())
    expect(container.querySelector('.katex')).toBeNull()
    expect(container.textContent).toBe('The licence is $5 and the add-on $12.')
  })

  it('reports a formula that does not parse, where the formula was', async () => {
    const { container } = body('Before $\\frac{$ after')
    await waitFor(() => expect(container.querySelector('[data-rich-note="math"]')).toBeTruthy())
    expect(container.textContent).toContain('Before')
    expect(container.textContent).toContain('after')
  })

  it('renders mathematics in the user bubble as well', async () => {
    const { container } = render(<UserMarkdown text={'I mean $x^2$ here'} />)
    await waitFor(() => expect(container.querySelector('.katex')).toBeTruthy())
  })
})

describe('diagrams in a message', () => {
  it('draws a mermaid fence', async () => {
    body('Here it is:\n\n```mermaid\ngraph TD; A-->B\n```\n')
    await waitFor(() => expect(screen.getByTestId('diagram')).toBeTruthy())
    expect(draw).toHaveBeenCalledWith(expect.any(String), 'graph TD; A-->B')
  })

  it('turns a diagram that does not parse into a sentence, with the message intact', async () => {
    draw.mockRejectedValue(new Error('Parse error on line 2: Expecting NEWLINE, got EOF'))
    const { container } = body(
      'Before the diagram.\n\n```mermaid\nflowchart TD\n  A[--> \n```\n\nAfter it.',
    )
    await waitFor(() => expect(container.querySelector('[data-rich-note="diagram"]')).toBeTruthy())
    expect(container.textContent).toContain('richText.diagramError')
    expect(container.textContent).toContain('Expecting NEWLINE, got EOF')
    expect(container.textContent).toContain('A[--> ')
    expect(container.textContent).toContain('Before the diagram.')
    expect(container.textContent).toContain('After it.')
    expect(container.querySelector('[data-diagram-state="ready"]')).toBeNull()
  })

  it('leaves every other fence on the code path', async () => {
    const { container } = body('```js\nconst a = 1\n```\n\n```mermaid\ngraph TD; A-->B\n```\n')
    await waitFor(() => expect(screen.getByTestId('diagram')).toBeTruthy())
    expect(container.querySelector('pre')?.textContent).toContain('const a = 1')
    expect(screen.getAllByTestId('diagram')).toHaveLength(1)
  })
})
