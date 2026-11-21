/**
 * W3-49 — wide markdown on a phone: tables, code, wide content.
 *
 * `body { overflow-x: hidden }` (globals.css) clips anything a chat bubble
 * pushes past its own edge. On a phone that means a wide GFM table loses the
 * columns past the bubble, a long code line is cut off, and a large image
 * disappears. jsdom has no layout engine, so these tests pin the class
 * contract (scroll container / width cap) that keeps each wide element
 * reachable. Each assertion fails again the moment that class is dropped from
 * the shared markdown overrides, on both the assistant and the user path
 * (user bubbles render markdown too).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MarkdownBody, UserMarkdown } from '@/components/dashboard/bubble/messageMarkdown'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

beforeEach(() => {
  document.body.innerHTML = ''
})

const TABLE = '| a | b |\n| --- | --- |\n| 1 | 2 |\n'
const LONG = `\`${'a'.repeat(80)}\`` // one unbreakable hex/hash-like token

describe('W3-49 — a wide GFM table stays reachable', () => {
  it('assistant path wraps the table in a horizontal scroll container', () => {
    render(<MarkdownBody text={TABLE} highlight={false} />)
    const wrap = screen.getByRole('table').parentElement
    expect(wrap).toBeTruthy()
    expect(String(wrap!.className)).toContain('overflow-x-auto')
    expect(String(wrap!.className)).toContain('max-w-full')
  })

  it('user path wraps the table in a horizontal scroll container too', () => {
    render(<UserMarkdown text={TABLE} />)
    const wrap = screen.getByRole('table').parentElement
    expect(wrap).toBeTruthy()
    expect(String(wrap!.className)).toContain('overflow-x-auto')
    expect(String(wrap!.className)).toContain('max-w-full')
  })
})

describe('W3-49 — code never clips the bubble', () => {
  it('assistant: a fenced block sits in a scrollable <pre>', () => {
    const { container } = render(
      <MarkdownBody text={'```js\nconst x = 1\n```'} highlight={false} />,
    )
    const pre = container.querySelector('pre')
    expect(pre).toBeTruthy()
    expect(String(pre!.className)).toContain('overflow-x-auto')
  })

  it('user: a fenced block sits in a scrollable, capped <pre>', () => {
    const { container } = render(<UserMarkdown text={'```txt\nlong line\n```'} />)
    const pre = container.querySelector('pre')
    expect(pre).toBeTruthy()
    expect(String(pre!.className)).toContain('overflow-x-auto')
    expect(String(pre!.className)).toContain('max-w-full')
  })

  it('inline code carries a break opportunity for a long token (both paths)', () => {
    const a = render(<MarkdownBody text={`hash ${LONG}`} highlight={false} />)
    const assistantCode = a.container.querySelector('code')
    expect(assistantCode).toBeTruthy()
    expect(String(assistantCode!.className)).toContain('[overflow-wrap:anywhere]')

    a.unmount()
    const u = render(<UserMarkdown text={`hash ${LONG}`} />)
    const userCode = u.container.querySelector('code')
    expect(userCode).toBeTruthy()
    expect(String(userCode!.className)).toContain('[overflow-wrap:anywhere]')
  })
})

describe('W3-49 — a wide image keeps its ratio inside the bubble', () => {
  it('assistant path caps the image width', () => {
    const { container } = render(
      <MarkdownBody text={'![shot](https://example.com/wide.png)'} highlight={false} />,
    )
    const img = container.querySelector('img')
    expect(img).toBeTruthy()
    expect(String(img!.className)).toContain('max-w-full')
  })

  it('user path caps the image width too', () => {
    const { container } = render(<UserMarkdown text={'![shot](https://example.com/wide.png)'} />)
    const img = container.querySelector('img')
    expect(img).toBeTruthy()
    expect(String(img!.className)).toContain('max-w-full')
  })
})
