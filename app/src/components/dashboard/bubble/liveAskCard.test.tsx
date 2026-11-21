/**
 * G1 — the live ask card: the question a RUNNING turn waits on.
 *
 * What it has to hold:
 *   - while the run waits, an option click answers THAT run (onAnswer with the label);
 *     it does not send a message, which is what the answer-text card does;
 *   - a question without options is answered as free text;
 *   - once the run is no longer waiting (answered / timeout / expired / restored
 *     history), the question stays readable and the options cannot be clicked.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import LiveAskCard from './liveAskCard'
import type { AskMessageState } from '@/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chat.askLive': 'The run is waiting for your answer',
        'chat.askAnswered': 'Answered',
        'chat.askTimedOut': `No answer within ${String(opts?.seconds)}s`,
        'chat.askExpired': 'This run is no longer waiting',
        'chat.askDefault': `Without an answer it continues on: ${String(opts?.value)}`,
        'chat.askOwn': 'Your own answer',
        'chat.send': 'Send',
        'chat.askRecommended': 'Recommended',
      }
      return map[key] ?? key
    },
  }),
}))

const WAITING: AskMessageState = {
  token: 'ask-1',
  question: 'Which branch?',
  options: [{ label: 'main' }, { label: 'wt/n1-ask' }],
  recommendation: 'main',
  timeoutS: 180,
  defaultAnswer: 'main',
  status: 'waiting',
}

describe('LiveAskCard', () => {
  it('offers the options while the run waits and answers THAT run', () => {
    const onAnswer = vi.fn()
    render(<LiveAskCard ask={WAITING} live onAnswer={onAnswer} />)

    expect(screen.getByTestId('live-ask-status').textContent).toContain(
      'The run is waiting for your answer',
    )
    // The default the run continues on is stated with the question (no silent hang).
    expect(screen.getByTestId('live-ask-status').textContent).toContain('main')
    fireEvent.click(screen.getByTestId('ask-option-1'))
    expect(onAnswer).toHaveBeenCalledWith('wt/n1-ask')
  })

  it('takes free text when the question offers no options', () => {
    const onAnswer = vi.fn()
    render(
      <LiveAskCard
        ask={{ ...WAITING, options: [], recommendation: undefined }}
        live
        onAnswer={onAnswer}
      />,
    )

    const input = screen.getByLabelText('Your own answer')
    fireEvent.change(input, { target: { value: 'take the second branch' } })
    fireEvent.click(screen.getByTestId('live-ask-send'))
    expect(onAnswer).toHaveBeenCalledWith('take the second branch')
  })

  it('keeps the question readable but not clickable once the answer landed', () => {
    const onAnswer = vi.fn()
    render(
      <LiveAskCard
        ask={{ ...WAITING, status: 'answered', answer: 'main' }}
        live
        onAnswer={onAnswer}
      />,
    )

    expect(screen.getByTestId('live-ask-status').textContent).toContain('Answered: main')
    expect(screen.getByTestId('ask-option-0')).toBeDisabled()
    fireEvent.click(screen.getByTestId('ask-option-0'))
    expect(onAnswer).not.toHaveBeenCalled()
  })

  it('names the default the same run continued on after the timeout', () => {
    render(<LiveAskCard ask={{ ...WAITING, status: 'timeout' }} live onAnswer={vi.fn()} />)

    const status = screen.getByTestId('live-ask-status').textContent ?? ''
    expect(status).toContain('No answer within 180s')
    expect(status).toContain('Without an answer it continues on: main')
  })

  it('says the run went on when the answer arrived too late', () => {
    render(<LiveAskCard ask={{ ...WAITING, status: 'expired' }} live onAnswer={vi.fn()} />)

    expect(screen.getByTestId('live-ask-status').textContent).toContain(
      'This run is no longer waiting',
    )
    expect(screen.getByTestId('ask-option-0')).toBeDisabled()
  })

  it('a restored transcript carries the question without a live answer path', () => {
    const onAnswer = vi.fn()
    render(<LiveAskCard ask={WAITING} live={false} onAnswer={onAnswer} />)

    expect(screen.getByTestId('ask-option-0')).toBeDisabled()
    expect(screen.queryByTestId('live-ask-send')).toBeNull()
    fireEvent.click(screen.getByTestId('ask-option-0'))
    expect(onAnswer).not.toHaveBeenCalled()
  })
})
