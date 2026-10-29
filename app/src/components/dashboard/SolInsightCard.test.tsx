import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { SolInsightCard } from './SolInsightCard'
import { useChatStore } from '@/store/chatStore'

// SOL: the card names the rule a turn proved and opens the store that holds it.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'chat.solLearned': 'A rule for this project was learned',
        'chat.solOpen': 'View / Edit',
      }
      return map[key] ?? key
    },
    i18n: { language: 'en' },
  }),
}))

vi.mock('@/store/chatStore', () => ({
  useChatStore: vi.fn(),
}))

const useStore = vi.mocked(useChatStore)

type Insight = {
  id: string
  title: string
  kind: string
  trigger: string
  insight: string
  action: string
  verified_at: string
}

function state(insights: Insight[]) {
  return (sel: (s: { solInsights: Insight[] }) => unknown) => sel({ solInsights: insights })
}

const rule: Insight = {
  id: 'H1',
  title: 'The project tools are not on the shell PATH',
  kind: 'command-not-found',
  trigger: 'A tool call fails with command-not-found',
  insight: '`node` resolves to /opt/homebrew/bin/node',
  action: 'Prepend /opt/homebrew/bin to PATH',
  verified_at: '2026-10-29T14:00:00Z',
}

describe('SolInsightCard', () => {
  beforeEach(() => {
    useStore.mockReset()
  })

  it('stays out of the way when the turn proved nothing', () => {
    useStore.mockImplementation(state([]) as never)
    const { container } = render(<SolInsightCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('names every rule the turn proved', () => {
    useStore.mockImplementation(state([rule, { ...rule, id: 'H2', title: 'Second rule' }]) as never)
    render(<SolInsightCard />)
    expect(screen.getByTestId('sol-insight')).toBeTruthy()
    expect(screen.getByText('A rule for this project was learned')).toBeTruthy()
    expect(screen.getByText(rule.title)).toBeTruthy()
    expect(screen.getByText('Second rule')).toBeTruthy()
  })

  it('opens the memory tab that holds the rule', () => {
    useStore.mockImplementation(state([rule]) as never)
    const seen: Array<{ name: string; tab?: string }> = []
    const onTab = (event: Event) => {
      seen.push({ name: 'tab', tab: (event as CustomEvent<{ tab?: string }>).detail?.tab })
    }
    const onOpen = () => seen.push({ name: 'open' })
    window.addEventListener('ephe:settings-tab', onTab)
    window.addEventListener('ephe:open-settings', onOpen)
    try {
      render(<SolInsightCard />)
      fireEvent.click(screen.getByTestId('sol-insight-open'))
    } finally {
      window.removeEventListener('ephe:settings-tab', onTab)
      window.removeEventListener('ephe:open-settings', onOpen)
    }
    expect(seen).toEqual([
      { name: 'tab', tab: 'memory' },
      { name: 'open' },
    ])
  })
})
