/**
 * The diagram states, against a mocked mermaid.
 *
 * What is asserted here is the contract with mermaid, not mermaid itself: the config
 * the loader hands it (the two flags that make a hostile diagram harmless), the SVG
 * it returns reaching the DOM, and a rejection arriving as a sentence with the source
 * still on screen. The real library runs in `MermaidChart.hostile.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import mermaid from 'mermaid'
import MermaidChart from './MermaidChart'

vi.mock('mermaid', () => ({
  default: { initialize: vi.fn(), render: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const initialize = mermaid.initialize as unknown as ReturnType<typeof vi.fn>
const renderDiagram = mermaid.render as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  // Only the render mock is reset: the loader caches its module-scope promise for
  // the whole file, so the base `initialize` call stays in the history of whichever
  // test happened to load it.
  renderDiagram.mockReset()
})

describe('MermaidChart', () => {
  it('draws the SVG mermaid returns', async () => {
    renderDiagram.mockResolvedValue({ svg: '<svg data-testid="diagram"></svg>' })
    const { container } = render(<MermaidChart code={'graph TD; A-->B'} />)

    await waitFor(() =>
      expect(container.querySelector('[data-diagram-state="ready"]')).toBeTruthy(),
    )
    expect(screen.getByTestId('diagram')).toBeTruthy()
    expect(renderDiagram).toHaveBeenCalledWith(expect.any(String), 'graph TD; A-->B')
  })

  it('initialises mermaid with the guards a hostile document needs', async () => {
    renderDiagram.mockResolvedValue({ svg: '<svg></svg>' })
    render(<MermaidChart code={'graph TD; A-->B'} />)

    await waitFor(() =>
      expect(initialize).toHaveBeenCalledWith(
        expect.objectContaining({
          startOnLoad: false,
          securityLevel: 'strict',
          suppressErrorRendering: true,
        }),
      ),
    )
  })

  it('shows the source while the renderer is still loading', () => {
    renderDiagram.mockReturnValue(new Promise(() => {}))
    const { container } = render(<MermaidChart code={'graph TD; A-->B'} />)

    expect(container.querySelector('[data-diagram-state="pending"]')?.textContent).toContain(
      'graph TD; A-->B',
    )
  })

  it('turns a parse failure into a sentence and keeps the source', async () => {
    renderDiagram.mockRejectedValue(
      new Error('Parse error on line 2:\n  A[--> ]\n        ^\nExpecting NEWLINE'),
    )
    const { container } = render(
      <div>
        <p>before the diagram</p>
        <MermaidChart code={'flowchart TD\n  A[--> '} />
        <p>after the diagram</p>
      </div>,
    )

    await waitFor(() => expect(container.querySelector('[data-rich-note="diagram"]')).toBeTruthy())
    const note = container.querySelector('[data-rich-note="diagram"]')
    expect(note?.textContent).toContain('richText.diagramError')
    expect(note?.textContent).toContain('Parse error on line 2: A[--> ] ^ Expecting NEWLINE')
    expect(note?.textContent).toContain('A[--> ')
    expect(screen.getByText('before the diagram')).toBeTruthy()
    expect(screen.getByText('after the diagram')).toBeTruthy()
  })

  it('reports a rejected render the same way', async () => {
    renderDiagram.mockRejectedValue(new Error('chunk unavailable'))
    const { container } = render(<MermaidChart code={'graph TD; A-->B'} />)

    await waitFor(() => expect(container.querySelector('[data-rich-note="diagram"]')).toBeTruthy())
    expect(container.querySelector('[data-rich-note="diagram"]')?.textContent).toContain(
      'chunk unavailable',
    )
  })
})
