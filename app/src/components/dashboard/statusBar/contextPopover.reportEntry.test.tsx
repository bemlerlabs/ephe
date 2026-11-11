// The chat's context pop-up is the second entry into the report: it closes itself
// and asks the shell for the settings tab, the same event pair every other surface
// uses. Esc closes the pop-up too — the old handler clicked a test id that no
// longer existed.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

import StatusBar from '@/components/dashboard/StatusBar'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getContextBudget: vi.fn(async () => ({
      window_tokens: 8192,
      window_source: 'env',
      estimated_tokens: 1200,
      percent: 14.65,
      message_count: 4,
      tokenizer: 'tiktoken-bpe',
      compaction_active: false,
      breakdown: [],
    })),
  }
})

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: Record<string, unknown>) => unknown) =>
    sel({ sessions: [], currentSession: null, enginePricing: null, lastTurnUsage: null }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const messages: ChatMessage[] = [
  { id: 'm1', role: 'user', content: 'one', timestamp: Date.now() },
] as ChatMessage[]

afterEach(cleanup)

async function openPopover() {
  // The budget request resolves after mount; letting it settle inside act keeps
  // React's warning out of the run without changing what the test sees.
  await act(async () => {
    render(<StatusBar messages={messages} sessionId="s1" backendOnline engineOnline />)
  })
  fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
  return screen.getByTestId('context-popover')
}

describe('the context pop-up report entry', () => {
  it('asks for the context report tab and closes the pop-up', async () => {
    const onTab = vi.fn()
    const onOpen = vi.fn()
    window.addEventListener('ephe:settings-tab', onTab)
    window.addEventListener('ephe:open-settings', onOpen)
    try {
      await openPopover()
      fireEvent.click(screen.getByTestId('context-popover-report'))
      expect((onTab.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({ tab: 'contextReport' })
      expect(onOpen).toHaveBeenCalledTimes(1)
      expect(screen.queryByTestId('context-popover')).toBeNull()
    } finally {
      window.removeEventListener('ephe:settings-tab', onTab)
      window.removeEventListener('ephe:open-settings', onOpen)
    }
  })

  it('closes on Esc', async () => {
    await openPopover()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('context-popover')).toBeNull()
  })
})
