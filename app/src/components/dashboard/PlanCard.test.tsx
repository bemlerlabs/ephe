import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { parsePlanCard } from '@/lib/planCardModel'
import PlanCard from './PlanCard'
import { useChatStore } from '@/store/chatStore'

// Fixed table, the AskUserQuestionCard.test pattern. The rest of the module stays real:
// PlanCard reads the session's composer mode from the shared store, and the store's
// module graph initialises i18n (src/i18n.ts), which calls initReactI18next.
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: Record<string, unknown>) => {
        const map: Record<string, string> = {
          'chat.planTitle': 'Plan',
          'chat.planAccept': 'Accept',
          'chat.planEdit': 'Modify',
          // The accept line the engine now reads: it names the mode change instead of the
          // bare "Plan accepted — proceed." that left the composer in `plan`.
          'chat.planAcceptMsg':
            'Plan accepted — the composer left Plan mode, so the write tools are available now. Run this plan now, step by step, and do each file write in one tool call:',
          'chat.planEditMsg': 'Adjust the plan to exactly these steps:',
          'chat.planEditSend': 'Send the edited plan',
          'chat.planEditCancel': 'Cancel',
          'chat.planAccepted': 'Accepted — the composer left Plan mode; the steps run in {{mode}}.',
          'chat.planRunning': 'Running.',
          'chat.planStepAria': 'Plan step {{n}}',
          // The card reads the mode's short title from the same hint the mode menu uses.
          'chat.modeHint.edit-auto':
            'Edit auto — the write tools run without asking, the rest still asks',
        }
        const raw = map[key] ?? key
        return opts
          ? raw.replace('{{n}}', String(opts.n)).replace('{{mode}}', String(opts.mode))
          : raw
      },
    }),
  }
})

beforeEach(() => {
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
})

const DRAFT = parsePlanCard(
  [
    '## Plan',
    '- [ ] Read the three route files the request names',
    '- [ ] Add the failing case to the existing test family',
    '- [ ] Change the handler and keep the response shape',
  ].join('\n'),
)!

const LIVE = parsePlanCard(
  ['## Plan · 1/3', '- [x] Read the manifest', '- [>] Run the test suite', '- [ ] Summarize'].join(
    '\n',
  ),
)!

describe('PlanCard', () => {
  it('renders numbered steps with the progress count', () => {
    render(<PlanCard spec={LIVE} onPick={() => undefined} />)
    expect(screen.getByTestId('plan-progress').textContent).toBe('1/3')
    expect(screen.getByText('Read the manifest')).toBeTruthy()
    expect(screen.getByTestId('plan-item-0').className).toBeTruthy()
  })

  it('strikethroughs completed steps only', () => {
    render(<PlanCard spec={LIVE} onPick={() => undefined} />)
    expect(screen.getByText('Read the manifest').className).toContain('line-through')
    expect(screen.getByText('Run the test suite').className).not.toContain('line-through')
  })

  it('carries the failed and cancelled marks', () => {
    const spec = parsePlanCard('## Plan\n- [ ] a\n- [!] Explode\n- [-] Skipped')!
    render(<PlanCard spec={spec} onPick={() => undefined} />)
    expect(screen.getByTestId('plan-item-1').getAttribute('data-status')).toBe('failed')
    expect(screen.getByTestId('plan-item-2').getAttribute('data-status')).toBe('cancelled')
  })

  it('accept leaves Plan mode and hands the plan to the turn that runs it', () => {
    const onPick = vi.fn()
    useChatStore.getState().createSession('Plan accept')
    const sessionId = useChatStore.getState().activeSessionId!
    useChatStore.getState().setSessionMode(sessionId, 'plan')
    render(<PlanCard spec={DRAFT} onPick={onPick} />)
    fireEvent.click(screen.getByTestId('plan-accept'))

    // The exit the user can read: the session's composer mode moved off `plan` — the chip
    // is bound to this value, and a turn sent now carries it to the engine.
    expect(useChatStore.getState().sessions.find((s) => s.id === sessionId)?.mode).toBe('edit-auto')
    expect(useChatStore.getState().currentSession?.mode).toBe('edit-auto')

    // The turn carries the confirmed plan, not a bare go-ahead.
    expect(onPick).toHaveBeenCalledTimes(1)
    const sent = String(onPick.mock.calls[0]![0])
    expect(sent).toContain('## Plan')
    expect(sent).toContain('- [ ] Read the three route files the request names')
    expect(sent).toContain('- [ ] Change the handler and keep the response shape')
    expect(sent).not.toBe('Plan accepted — proceed.')

    expect(screen.queryByTestId('plan-accept')).toBeNull()
    expect(screen.getByTestId('plan-card').getAttribute('data-state')).toBe('accepted')
    expect(screen.getByTestId('plan-accepted').textContent).toContain('Edit auto')
  })

  it('offers no gate once a step has moved', () => {
    render(<PlanCard spec={LIVE} onPick={() => undefined} />)
    expect(screen.queryByTestId('plan-accept')).toBeNull()
    expect(screen.queryByTestId('plan-edit')).toBeNull()
    expect(screen.getByTestId('plan-running-note')).toBeTruthy()
  })

  it('modify edits the steps and sends the edited plan in the block shape', () => {
    const onPick = vi.fn()
    render(<PlanCard spec={DRAFT} onPick={onPick} />)
    fireEvent.click(screen.getByTestId('plan-edit'))
    expect(screen.getAllByTestId(/^plan-step-input-/)).toHaveLength(3)
    fireEvent.change(screen.getByTestId('plan-step-input-2'), {
      target: { value: 'Change the handler and add a migration' },
    })
    fireEvent.click(screen.getByTestId('plan-edit-send'))
    const sent = String(onPick.mock.calls[0]![0])
    expect(sent).toContain('Adjust the plan to exactly these steps:')
    expect(sent).toContain('## Plan\n- [ ] Read the three route files the request names')
    expect(sent).toContain('- [ ] Change the handler and add a migration')
  })

  it('cancel leaves the plan untouched and sends nothing', () => {
    const onPick = vi.fn()
    render(<PlanCard spec={DRAFT} onPick={onPick} />)
    fireEvent.click(screen.getByTestId('plan-edit'))
    fireEvent.change(screen.getByTestId('plan-step-input-0'), { target: { value: 'Discarded' } })
    fireEvent.click(screen.getByTestId('plan-edit-cancel'))
    expect(onPick).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('plan-edit'))
    expect(screen.getByTestId<HTMLInputElement>('plan-step-input-0').value).toBe(
      'Read the three route files the request names',
    )
  })

  it('shows the steps while the answer streams and keeps the gate shut until it ends', () => {
    const onPick = vi.fn()
    const { rerender } = render(<PlanCard spec={DRAFT} onPick={onPick} streaming />)

    // The card is readable while the answer arrives: the steps are there, the gate is not.
    expect(screen.getByTestId('plan-card')).toBeTruthy()
    expect(screen.getByText('Read the three route files the request names')).toBeTruthy()
    expect(screen.queryByTestId('plan-accept')).toBeNull()

    // A half-written line renders as a shorter step, and the next frame lengthens it.
    const partial = parsePlanCard('## Plan\n- [ ] Read the three route fil')
    expect(partial).not.toBeNull()
    rerender(<PlanCard spec={partial!} onPick={onPick} streaming />)
    expect(screen.getByText('Read the three route fil')).toBeTruthy()

    // The same draft with the turn finished: the gate opens, and only then.
    rerender(<PlanCard spec={DRAFT} onPick={onPick} />)
    expect(screen.getByTestId('plan-accept')).toBeTruthy()
  })
})
