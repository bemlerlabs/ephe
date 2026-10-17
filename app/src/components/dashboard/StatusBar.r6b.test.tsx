/** R8: the meter states where its window comes from.
 *
 * The active engine does not state its window (measured on /v1/models: id,
 * object, owned_by). 8.192 stays as a computed value — but a bar showing
 * „57 %" against an assumed window without saying so presents
 * a guess as a measurement.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (io) => ({
  ...(await io<typeof import('@/lib/api')>()),
  getContextBudget: vi.fn(async () => ({}) as never),
}))
vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: { sessions: unknown[] }) => unknown) =>
    sel({ sessions: [{ id: 'a', messages: [] }] }),
}))
// The window number is what this test reads, so the language belongs to the
// test: '262,144' is only right because the runner happened to speak English.
const sprache = vi.hoisted(() => ({ current: 'en' }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => `${key}:${JSON.stringify(opts ?? {})}`,
    i18n: { language: sprache.current },
  }),
}))

const msgs: ChatMessage[] = [{ id: 'u-1', role: 'user', content: 'x'.repeat(9000), timestamp: 1 }]

async function hinweis(budget: Record<string, unknown>) {
  vi.mocked(getContextBudget).mockResolvedValue(budget as never)
  render(<StatusBar messages={msgs} />)
  const meter = await screen.findByTitle(/statusBar\.(window|contextMeterHint)/)
  return meter.getAttribute('title') ?? ''
}

describe('StatusBar R8 — Herkunft des Fensters im Tooltip', () => {
  it('sagt „angenommen", wenn die Sonde nichts fand (legacy)', async () => {
    const titel = await hinweis({
      message_count: 3,
      estimated_tokens: 4729,
      window_tokens: 8192,
      window_source: 'legacy',
      percent: 57.7,
      char_count: 19000,
    })
    expect(titel).toContain('statusBar.windowAssumed')
  })

  it('nennt die Engine, wenn sie das Feld liefert', async () => {
    const titel = await hinweis({
      message_count: 3,
      estimated_tokens: 4729,
      window_tokens: 262144,
      window_source: 'engine',
      percent: 2,
      char_count: 19000,
    })
    expect(titel).toContain('statusBar.windowEngine')
    expect(titel).toContain('262,144')
  })

  it('zeigt die Zahl, nicht nur die Quelle', async () => {
    const titel = await hinweis({
      message_count: 3,
      estimated_tokens: 100,
      window_tokens: 131072,
      window_source: 'tier',
      percent: 1,
      char_count: 400,
    })
    expect(titel).toContain('statusBar.windowTier')
    expect(titel).toContain('131,072')
  })

  it('sets the German separator for the same number when the interface is German', async () => {
    sprache.current = 'de'
    const engine = await hinweis({
      message_count: 3,
      estimated_tokens: 4729,
      window_tokens: 262144,
      window_source: 'engine',
      percent: 2,
      char_count: 19000,
    })
    expect(engine).toContain('statusBar.windowEngine')
    expect(engine).toContain('262.144')
    sprache.current = 'en'
  })
})
