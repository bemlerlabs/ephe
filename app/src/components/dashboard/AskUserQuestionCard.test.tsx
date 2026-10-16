import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { parseAskUserQuestion } from '@/lib/askUserQuestion'
import AskUserQuestionCard from './AskUserQuestionCard'

// i18n mock (like SchedulerPanel.test — a fixed DE table)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'chat.askRecommended': 'Empfohlen',
        'chat.askTakeover': 'Übernehmen',
      }
      return map[key] ?? key
    },
  }),
}))

const SPEC = {
  question: 'Welches Theme?',
  options: [
    { label: 'Black Forest', description: 'Tannengrün' },
    { label: 'Nord', description: 'Kühl' },
  ],
  recommendation: 'Black Forest',
}

describe('parseAskUserQuestion', () => {
  it('parses a fenced json block', () => {
    const text = [
      'Antwort.',
      '```json',
      '{"question": "Q?", "options": [{"label": "A"}, {"label": "B"}]}',
      '```',
    ].join('\n')
    const spec = parseAskUserQuestion(text)
    expect(spec).not.toBeNull()
    expect(spec!.question).toBe('Q?')
    expect(spec!.options).toHaveLength(2)
    expect(spec!.options[0]?.label).toBe('A')
  })

  it('parses a bare block with trailing commas tolerated', () => {
    const spec = parseAskUserQuestion(
      'Vortext {"question": "Q?", "options": ["A", "B",], "multiSelect": true,}',
    )
    expect(spec).not.toBeNull()
    expect(spec!.multiSelect).toBe(true)
    expect(spec!.options[1]?.label).toBe('B')
  })

  it('returns null without a valid block', () => {
    expect(parseAskUserQuestion('nur text')).toBeNull()
    expect(parseAskUserQuestion('{"options": ["A"]}')).toBeNull()
    expect(parseAskUserQuestion(undefined)).toBeNull()
  })
})

describe('AskUserQuestionCard', () => {
  it('renders numbered options with description and recommendation marker', () => {
    render(<AskUserQuestionCard spec={SPEC} onPick={vi.fn()} />)
    expect(screen.getByText('Welches Theme?')).toBeTruthy()
    expect(screen.getByText('Black Forest')).toBeTruthy()
    expect(screen.getByText('Tannengrün')).toBeTruthy()
    expect(screen.getByText(/Empfohlen/)).toBeTruthy()
  })

  it('single-select: click sends the label', () => {
    const onPick = vi.fn()
    render(<AskUserQuestionCard spec={SPEC} onPick={onPick} />)
    fireEvent.click(screen.getByTestId('ask-option-1'))
    expect(onPick).toHaveBeenCalledWith('Nord')
  })

  it('multi-select: toggle + take-over joins labels', () => {
    const onPick = vi.fn()
    render(<AskUserQuestionCard spec={{ ...SPEC, multiSelect: true }} onPick={onPick} />)
    fireEvent.click(screen.getByTestId('ask-option-0'))
    fireEvent.click(screen.getByTestId('ask-option-1'))
    fireEvent.click(screen.getByTestId('ask-takeover'))
    expect(onPick).toHaveBeenCalledWith('Black Forest, Nord')
  })

  it('take-over is disabled until something is picked', () => {
    render(<AskUserQuestionCard spec={{ ...SPEC, multiSelect: true }} onPick={vi.fn()} />)
    expect((screen.getByTestId('ask-takeover') as HTMLButtonElement).disabled).toBe(true)
  })
})
