/** R6/S2: one row, one counting basis.
 *
 * Finding 2026-10-07, read off the running product: „50.48% · 4.135 tok ·
 * 5.424 frei" — used and percent came from the server mirror, „frei" (free) from
 * the frontend estimate. 4.135 + 5.424 = 9.559, the window is 8.192. The
 * row contradicted its own arithmetic.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})
vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: { sessions: unknown[] }) => unknown) =>
    sel({ sessions: [{ id: 'a', messages: [] }] }),
}))
// The language is set here, not inherited: a test that compares its expectation
// with the machine's own locale is blind — it stays green whatever the product
// does, and goes red only because the runner happens to speak English.
const sprache = vi.hoisted(() => ({ current: 'en' }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // The key plus its interpolated values: the row's free figure carries the window
    // beside it since F1, and a mock that drops the values cannot see that.
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${JSON.stringify(opts)}` : key,
    i18n: { language: sprache.current },
  }),
}))

const msgs: ChatMessage[] = [{ id: 'u-1', role: 'user', content: 'x'.repeat(20000), timestamp: 1 }]

describe('StatusBar R6 — benutzt und frei aus derselben Zählung', () => {
  it('rechnet frei als Fenster minus Spiegel, solange der Spiegel lebt', async () => {
    vi.mocked(getContextBudget).mockResolvedValue({
      message_count: 3,
      char_count: 16540,
      estimated_tokens: 4135,
      window_tokens: 8192,
      percent: 50.48,
      compaction_threshold: 28,
      compaction_active: false,
    } as never)
    render(<StatusBar messages={msgs} />)
    // The label exists on the first render, carrying the offline estimate; the
    // mirror arrives one tick later. Matching the label would pass on either
    // number and lose the race in CI, so the wait is for the mirror's own value.
    const frei = await screen.findByText(/4,057/)
    // Pinned to the app language, not to (8192 - 4135).toLocaleString(): the
    // self-referential form follows the machine and can never see the defect.
    expect(frei.textContent).toContain('4,057')
  })

  it('writes the free number with the German separator when the interface is German', async () => {
    sprache.current = 'de'
    vi.mocked(getContextBudget).mockResolvedValue({
      message_count: 3,
      char_count: 16540,
      estimated_tokens: 4135,
      window_tokens: 8192,
      percent: 50.48,
      compaction_threshold: 28,
      compaction_active: false,
    } as never)
    render(<StatusBar messages={msgs} />)
    const frei = await screen.findByText(/4\.057/)
    expect(frei.textContent).toContain('4.057')
    sprache.current = 'en'
  })

  it('bleibt bei der Schätzung, solange der Spiegel nichts meldet', async () => {
    vi.mocked(getContextBudget).mockResolvedValue({} as never)
    render(<StatusBar messages={msgs} />)
    const frei = await screen.findByText(/statusBar.contextFree/)
    expect(frei.textContent).toMatch(/\d/)
    expect(frei.textContent).not.toContain('8.192')
  })
})
