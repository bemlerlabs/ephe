// P4 finding 6: the status bar's storage pill truncated as one whole string —
// that cut off the NUMBER ("48 Sitzun…"), not the word. // language-gate: ignore — the quote is the truncated German status-bar string the pill renders
// The pill now renders the translated string piece by piece: the digits are
// `shrink-0`, the text in between has to give way.
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: { sessions: unknown[] }) => unknown) =>
    sel({
      sessions: Array.from({ length: 48 }, (_, i) => ({ id: `s${i}`, messages: [] })),
    }),
}))

const STRINGS: Record<string, string> = {
  'statusBar.storage': '{{count}} Sitzungen · ~{{mb}} MB',
  'statusBar.storageHint': 'Browser-Cache (IndexedDB) auf dem Geraet — {{count}} Sitzungen',
  'statusBar.contextFree': 'frei',
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const pattern = STRINGS[key]
      if (!pattern) return key
      return pattern
        .replace('{{count}}', String(opts?.count ?? ''))
        .replace('{{mb}}', String(opts?.mb ?? ''))
    },
    // The fixture strings above are German, so this test runs the German surface.
    i18n: { language: 'de' },
  }),
}))

const msg = (): ChatMessage[] => [
  { id: 'u-1', role: 'user', content: 'x'.repeat(420), timestamp: Date.now() },
]

const NUMBER_CLASS = 'shrink-0'
const TEXT_CLASS = 'overflow-hidden'

describe('Statuszeile: Ziffern werden nie abgeschnitten (P4 Befund 6)', () => {
  it('die Zahl-Stuecke sind undisponibel, das Wort dazwichen darf weichen', () => {
    render(<StatusBar messages={msg()} />)
    const chip = screen.getByTestId('statusbar-storage-chip')
    const numbers = screen.getAllByTestId('statusbar-storage-number')
    expect(numbers.length).toBe(2)
    expect(numbers[0]!.textContent).toBe('48')
    // The fixture interface is German, so the MB piece arrives with a comma
    // separator since D5; the rule under test is that the number is whole.
    expect(numbers[1]!.textContent).toMatch(/^\d+[.,]\d+$/)
    for (const n of numbers) {
      expect(n.className).toContain(NUMBER_CLASS)
      expect(n.className).not.toContain('overflow-hidden')
      expect(n.className).not.toContain('text-ellipsis')
    }
    // The word pieces (" Sitzungen · ~" and " MB") carry the truncation — never the number. // language-gate: ignore — both quotes are the German fixture word pieces asserted below
    const words = Array.from(chip.children).filter((el) => !el.hasAttribute('data-testid'))
    expect(words.length).toBe(2)
    expect(words[0]!.textContent).toBe(' Sitzungen · ~')
    for (const w of words) {
      expect(w.className).toContain(TEXT_CLASS)
      expect(w.className).toContain('text-ellipsis')
      expect(w.className).toContain('min-w-0')
    }
  })

  it('der sichtbare Text bleibt die ganze Zeile ohne Auslassungszeichen in den Zahlen', () => {
    render(<StatusBar messages={msg()} />)
    const chip = screen.getByTestId('statusbar-storage-chip')
    expect(chip.textContent).toMatch(/^48 Sitzungen · ~\d+[.,]\d+ MB$/)
    expect(chip.textContent).not.toMatch(/…|\.\.\./)
    for (const n of screen.getAllByTestId('statusbar-storage-number')) {
      expect(n.textContent).not.toMatch(/…/)
    }
  })

  it('Pille liegt in einer flex-Zeile, damit min-w-0 wirklich weichen kann', () => {
    render(<StatusBar messages={msg()} />)
    expect(screen.getByTestId('statusbar-storage-chip').className).toContain('flex')
  })
})
