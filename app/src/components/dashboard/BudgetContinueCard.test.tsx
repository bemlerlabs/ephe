import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { BudgetContinueCard } from './BudgetContinueCard'
import { useChatStore } from '@/store/chatStore'

// QD-015 Z2: the cap end gets a way on. The card reads the numbers the server
// reported and calls the continuation once — never while a turn is running.

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chat.continueTitle': 'Tool budget used up',
        'chat.continueBody': 'This turn used all {{cap}} rounds and stopped unfinished.',
        'chat.continueButton': 'Continue (+{{extra}} rounds)',
      }
      const pattern = map[key] ?? key
      if (!opts) return pattern
      return pattern
        .replace('{{cap}}', String(opts.cap ?? ''))
        .replace('{{extra}}', String(opts.extra ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

vi.mock('@/store/chatStore', () => ({
  useChatStore: vi.fn(),
}))

const useStore = vi.mocked(useChatStore)

function state(notice: { cap: number; extra: number } | null, typing = false) {
  return (sel: (s: { budgetNotice: typeof notice; isTyping: boolean }) => unknown) =>
    sel({ budgetNotice: notice, isTyping: typing })
}

describe('BudgetContinueCard', () => {
  beforeEach(() => {
    useStore.mockReset()
  })

  it('stays out of the way while nothing ran out', () => {
    useStore.mockImplementation(state(null) as never)
    const { container } = render(<BudgetContinueCard onContinue={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('names the cap and the rounds it adds', () => {
    useStore.mockImplementation(state({ cap: 25, extra: 10 }) as never)
    render(<BudgetContinueCard onContinue={() => {}} />)
    expect(screen.getByText(/25 rounds/)).toBeTruthy()
    expect(screen.getByTestId('budget-continue-button').textContent).toContain('+10')
  })

  it('continues once on click', () => {
    useStore.mockImplementation(state({ cap: 25, extra: 10 }) as never)
    const onContinue = vi.fn()
    render(<BudgetContinueCard onContinue={onContinue} />)
    fireEvent.click(screen.getByTestId('budget-continue-button'))
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('is not offered while a turn is still running', () => {
    useStore.mockImplementation(state({ cap: 25, extra: 10 }, true) as never)
    const { container } = render(<BudgetContinueCard onContinue={() => {}} />)
    expect(container.firstChild).toBeNull()
  })
})
