/**
 * P6 (user request, ref-01 parity): links in the chat open the panel URL pane.
 *
 * GIVEN  a finished assistant answer containing a Markdown link
 * WHEN   the user clicks that link
 * THEN   PREVIEW_OPEN_EVENT fires with the URL (browser pane, B5 dedup) and
 *        the browser navigation is prevented; mailto: is NOT intercepted.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MessageBubble from './MessageBubble'
import type { ChatMessage } from '@/types'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'de' } }),
}))

const MSG: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content:
    'Quelle: [Artikel](https://example.com/article) — lokal: [Datei](/api/file?path=a.md) und [Mail](mailto:x@example.com)',
  timestamp: Date.now(),
  streaming: false,
}

describe('MessageBubble Link-Routing (P6)', () => {
  it('routet http(s)- und interne Links ins Panel, mailto nicht', () => {
    const seen: { url?: string; tab?: string }[] = []
    const listener = (e: Event) =>
      seen.push((e as CustomEvent).detail as { url?: string; tab?: string })
    window.addEventListener('ephe:preview-open', listener)
    try {
      render(<MessageBubble message={MSG} />)
      const link = screen.getByText('Artikel')
      expect(link.tagName).toBe('A')
      fireEvent.click(link)
      expect(seen[seen.length - 1]?.url).toBe('https://example.com/article')

      const local = screen.getByText('Datei')
      fireEvent.click(local)
      expect(seen[seen.length - 1]?.url).toBe('/api/file?path=a.md')

      const mail = screen.getByText('Mail')
      fireEvent.click(mail)
      // mailto: keeps the browser default — no panel event
      expect(seen.filter((d) => d.url?.startsWith('mailto'))).toHaveLength(0)
    } finally {
      window.removeEventListener('ephe:preview-open', listener)
    }
  })
})
