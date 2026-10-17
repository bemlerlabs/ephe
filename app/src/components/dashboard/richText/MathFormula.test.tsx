/**
 * The two formula states that matter.
 *
 * KaTeX itself is not mocked here: the point is that a real formula reaches the DOM
 * and that a real parse error reaches the reader as a sentence.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MathBlock, MathInline } from './MathFormula'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

describe('MathInline', () => {
  it('sets a formula through KaTeX once the chunk has loaded', async () => {
    const { container } = render(<MathInline>{'\\pi r^2'}</MathInline>)
    expect(container.textContent).toBe('\\pi r^2')

    await waitFor(() => expect(container.querySelector('.katex')).toBeTruthy())
    expect(container.textContent).toContain('π')
  })

  it('reports a formula that does not parse instead of dropping it', async () => {
    const { container } = render(<MathInline>{'\\frac{'}</MathInline>)

    await waitFor(() => expect(container.querySelector('[data-rich-note="math"]')).toBeTruthy())
    const note = container.querySelector('[data-rich-note="math"]')
    expect(note?.textContent).toContain('richText.mathError')
    expect(note?.textContent).toContain('\\frac{')
  })
})

describe('MathBlock', () => {
  it('sets a display formula in display mode', async () => {
    const { container } = render(<MathBlock>{'\\int_0^1 x\\,dx'}</MathBlock>)
    await waitFor(() => expect(container.querySelector('.katex-display')).toBeTruthy())
  })

  it('keeps a wide formula scrollable inside its own box', async () => {
    const { container } = render(<MathBlock>{'a + b'}</MathBlock>)
    await waitFor(() => expect(container.querySelector('[data-math-state="ready"]')).toBeTruthy())
    const box = container.querySelector('[data-math-state="ready"]')
    expect(box?.className).toContain('overflow-x-auto')
  })
})
