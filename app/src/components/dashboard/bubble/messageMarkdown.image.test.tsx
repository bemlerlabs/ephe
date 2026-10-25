import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MarkdownBody, UserMarkdown } from './messageMarkdown'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

beforeEach(() => {
  document.body.innerHTML = ''
})

const REMOTE = '![cat](https://images.example.test/cat.png)'

describe('S17: a remote image in an answer', () => {
  it('is fetched through the guarded proxy instead of the foreign host', () => {
    render(<MarkdownBody text={REMOTE} highlight={false} />)
    const img = screen.getByRole('img')
    expect(img.getAttribute('src')).toContain('/api/artifacts/proxy?')
    expect(img.getAttribute('src')).toContain(
      encodeURIComponent('https://images.example.test/cat.png'),
    )
    expect(img.getAttribute('src')).not.toContain('images.example.test/cat.png')
  })

  it('shows a fallback with retry when the bytes do not arrive', () => {
    render(<UserMarkdown text={REMOTE} />)
    fireEvent.error(screen.getByRole('img'))
    const fallback = screen.getByTestId('markdown-image-unavailable')
    expect(fallback.textContent).toContain('artifacts.imageUnavailable')
    fireEvent.click(fallback.querySelector('button')!)
    expect(screen.getByRole('img').getAttribute('src')).toContain('retry=1')
  })
})
