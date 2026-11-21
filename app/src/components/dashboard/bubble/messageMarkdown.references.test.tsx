import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MarkdownBody } from './messageMarkdown'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

// QD-015 W3: an answer links to the file it wrote. A workspace-relative or
// absolute path is not an app route — the browser 404'd on the app origin. Both
// images and links resolve through the guarded preview route now.

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

beforeEach(() => {
  document.body.replaceChildren()
})

function opened(): string[] {
  const urls: string[] = []
  const handler = (e: Event) => urls.push(String((e as CustomEvent<{ url: string }>).detail.url))
  window.addEventListener(PREVIEW_OPEN_EVENT, handler)
  ;(window as unknown as { __off?: () => void }).__off = () =>
    window.removeEventListener(PREVIEW_OPEN_EVENT, handler)
  return urls
}

describe('markdown references', () => {
  it('serves a workspace-relative image through /api/file', () => {
    render(<MarkdownBody text="![shot](docs/shot.png)" highlight={false} />)
    const src = decodeURIComponent(screen.getByRole('img').getAttribute('src') ?? '')
    expect(src).toContain('/api/file?path=docs/shot.png')
  })

  it('serves an absolute image path through /api/file', () => {
    render(<MarkdownBody text="![shot](/Users/someone/project/shot.png)" highlight={false} />)
    const src = decodeURIComponent(screen.getByRole('img').getAttribute('src') ?? '')
    expect(src).toContain('/api/file?path=/Users/someone/project/shot.png')
  })

  it('routes a relative file link into the preview pane instead of navigating', () => {
    const urls = opened()
    render(<MarkdownBody text="[report](reports/q3.pdf)" highlight={false} />)
    fireEvent.click(screen.getByRole('link'))
    expect(urls).toHaveLength(1)
    expect(decodeURIComponent(urls[0] ?? '')).toContain('/api/file?path=reports/q3.pdf')
    ;(window as unknown as { __off?: () => void }).__off?.()
  })

  it('keeps an app route link on its own URL', () => {
    const urls = opened()
    render(<MarkdownBody text="[settings](/settings)" highlight={false} />)
    fireEvent.click(screen.getByRole('link'))
    expect(urls).toEqual(['/settings'])
    ;(window as unknown as { __off?: () => void }).__off?.()
  })

  it('leaves a mailto link to the browser', () => {
    const urls = opened()
    render(<MarkdownBody text="[mail](mailto:a@b.test)" highlight={false} />)
    fireEvent.click(screen.getByRole('link'))
    expect(urls).toHaveLength(0)
    ;(window as unknown as { __off?: () => void }).__off?.()
  })
})
