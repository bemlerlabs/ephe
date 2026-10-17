/**
 * The hostile payload, against the real mermaid.
 *
 * Nothing is mocked here: a diagram written by a model and cut off mid-token has to
 * come out as a sentence where the diagram would be, with the message around it
 * intact and no staging element left on the page. jsdom cannot lay out an SVG, so a
 * *valid* diagram is not the assertion; the parse failure is, and it happens before
 * any layout.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import MermaidChart from './MermaidChart'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

describe('a diagram the engine made up', () => {
  it('lands as a sentence where the diagram would be', async () => {
    const { container } = render(
      <div>
        <p>before the diagram</p>
        <MermaidChart code={'flowchart TD\n  A[--> '} />
        <p>after the diagram</p>
      </div>,
    )

    await waitFor(
      () => expect(container.querySelector('[data-rich-note="diagram"]')).toBeTruthy(),
      {
        timeout: 15000,
      },
    )
    const note = container.querySelector('[data-rich-note="diagram"]')
    expect(note?.textContent).toContain('richText.diagramError')
    expect(note?.textContent).toContain('Parse error on line')
    expect(note?.textContent).toContain('flowchart TD')
    expect(screen.getByText('before the diagram')).toBeTruthy()
    expect(screen.getByText('after the diagram')).toBeTruthy()
    expect(document.querySelectorAll('[id^="dephe-diagram"]')).toHaveLength(0)
  })

  it('survives a diagram made of markup rather than syntax', async () => {
    const { container } = render(
      <MermaidChart code={'<img src=x onerror="alert(1)">\n<script>alert(2)</script>'} />,
    )

    await waitFor(
      () => expect(container.querySelector('[data-rich-note="diagram"]')).toBeTruthy(),
      {
        timeout: 15000,
      },
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.textContent).toContain('script')
  })
})
