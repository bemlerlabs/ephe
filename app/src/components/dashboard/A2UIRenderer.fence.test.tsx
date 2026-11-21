/**
 * P1-2 — the fence path into the renderer.
 *
 * `MarkdownBody` (bubble/messageMarkdown.tsx) hands every `<pre>` to `parseA2UI`
 * when `detectA2UI` is set, and falls back to `CodeBlock` for anything that is
 * not a surface. These tests pin the detection, the nesting seen through the
 * fence, and the code fallback for a payload the surface cannot use.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MarkdownBody } from '@/components/dashboard/bubble/messageMarkdown'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

beforeEach(() => {
  document.body.innerHTML = ''
})

const CARD = {
  surfaceId: 'demo',
  root: 'card1',
  components: [
    { id: 'card1', component: 'Card', label: 'Status', children: ['note'] },
    { id: 'note', component: 'Row', children: ['t1'] },
    { id: 't1', component: 'Text', text: 'All green' },
  ],
}

const fence = (lang: string, body: string) => '```' + lang + '\n' + body + '\n```\n'

describe('P1-2 — a fenced surface reaches the renderer', () => {
  it('renders a fence tagged a2ui as the component surface, children inside the Card', () => {
    const { container } = render(
      <MarkdownBody text={fence('a2ui', JSON.stringify(CARD))} highlight={false} detectA2UI />,
    )
    expect(screen.getByTestId('a2ui-root')).toBeTruthy()
    expect(screen.getByText('Status').parentElement).toContainElement(screen.getByText('All green'))
    expect(container.querySelector('pre')).toBeNull()
  })

  it('renders an untagged fence whose JSON declares a components array', () => {
    render(<MarkdownBody text={fence('json', JSON.stringify(CARD))} highlight={false} detectA2UI />)
    expect(screen.getByTestId('a2ui-root')).toBeTruthy()
  })

  it('leaves JSON that carries stray ids but no surface as code', () => {
    const payload = JSON.stringify({ id: 'a', component: 'Text', text: 'just an example' })
    const { container } = render(
      <MarkdownBody text={fence('json', payload)} highlight={false} detectA2UI />,
    )
    expect(screen.queryByTestId('a2ui-root')).toBeNull()
    expect(container.querySelector('pre')).toBeTruthy()
  })
})

describe('P1-2 — the fence falls back to CodeBlock', () => {
  it('renders a broken a2ui payload as code', () => {
    const { container } = render(
      <MarkdownBody text={fence('a2ui', '{"components": [')} highlight={false} detectA2UI />,
    )
    expect(screen.queryByTestId('a2ui-root')).toBeNull()
    expect(container.querySelector('pre')).toBeTruthy()
  })

  it('renders a valid surface as code when detectA2UI is off', () => {
    const { container } = render(
      <MarkdownBody text={fence('a2ui', JSON.stringify(CARD))} highlight={false} />,
    )
    expect(screen.queryByTestId('a2ui-root')).toBeNull()
    expect(container.querySelector('pre')).toBeTruthy()
  })

  it('renders an empty components list as code, not as an empty box', () => {
    const { container } = render(
      <MarkdownBody text={fence('a2ui', '{"components":[]}')} highlight={false} detectA2UI />,
    )
    expect(screen.queryByTestId('a2ui-root')).toBeNull()
    expect(container.querySelector('pre')).toBeTruthy()
  })
})
