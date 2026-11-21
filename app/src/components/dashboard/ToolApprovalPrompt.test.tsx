import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/react'
import ToolApprovalPrompt from '@/components/dashboard/ToolApprovalPrompt'
import type { ToolCall } from '@/store/chatStore'

// i18n mock (ToolApprovalPrompt uses useTranslation)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'chat.approvalNeeded': 'Bestätigung erforderlich',
        'chat.toolApproval.once': 'Allow once',
        'chat.toolApproval.remember': 'Remember for this session',
        'chat.toolApproval.deny': 'Deny',
        'chat.toolApproval.blastRadius': 'Blast radius:',
        'chat.toolApproval.headClosed': 'Approval for this tool',
        'chat.toolApproval.sending': 'Sending your answer…',
        'chat.toolApproval.allowedByYou': 'Allowed — by you',
        'chat.toolApproval.allowedByCompanion': 'Allowed — by the companion after its countdown',
        'chat.toolApproval.deniedByYou': 'Refused — by you',
        'chat.toolApproval.expiredOutcome':
          'Nobody answered before the approval window closed. Nothing ran.',
        'chat.toolApproval.spentOutcome':
          'The server does not hold this approval any more — it was answered elsewhere, or the run moved on.',
      }
      return map[key] ?? key
    },
  }),
}))

const tool = {
  id: 't1',
  name: 'run_shell',
  args: { command: 'ls' },
  status: 'waiting' as const,
}

describe('ToolApprovalPrompt (D1 a11y)', () => {
  it('is an alertdialog with an aria-label', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const dlg = container.querySelector('[role="alertdialog"]')
    expect(dlg).not.toBeNull()
    expect(dlg!.getAttribute('aria-label')).toContain('Bestätigung')
  })

  it('puts the initial focus on Deny (conservative: deny first)', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const deny = container.querySelector<HTMLButtonElement>('[data-testid="approval-deny"]')
    expect(deny?.contains(document.activeElement) || document.activeElement === deny).toBe(true)
  })

  it('focus trap: Tab cycles inside the dialog (Deny → Allow once → Deny)', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const once = container.querySelector<HTMLButtonElement>('[data-testid="approval-once"]')!
    const deny = container.querySelector<HTMLButtonElement>('[data-testid="approval-deny"]')!

    // Start: focus sits on Deny (auto-focus)
    deny.focus()

    // Tab from the last action (Deny) wraps to the first (Allow once)
    fireEvent.keyDown(deny, { key: 'Tab' })
    expect(document.activeElement).toBe(once)

    // Shift+Tab from the first action wraps back to the last (Deny)
    once.focus()
    fireEvent.keyDown(once, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(deny)
  })

  it('keeps the remember action inside the same trap when it is offered', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} rememberable onApprove={() => {}} onDeny={() => {}} />,
    )
    const once = container.querySelector<HTMLButtonElement>('[data-testid="approval-once"]')!
    const remember = container.querySelector<HTMLButtonElement>(
      '[data-testid="approval-remember"]',
    )!
    const deny = container.querySelector<HTMLButtonElement>('[data-testid="approval-deny"]')!

    fireEvent.keyDown(deny, { key: 'Tab' })
    expect(document.activeElement).toBe(once)

    // Middle action: neither edge, so the browser's own Tab order applies
    remember.focus()
    fireEvent.keyDown(remember, { key: 'Tab' })
    expect(document.activeElement).toBe(remember)

    once.focus()
    fireEvent.keyDown(once, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(deny)
  })

  it('Esc fires onDeny (the escape path)', () => {
    let denied = 0
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => denied++} />,
    )
    const dlg = container.querySelector('[role="alertdialog"]')!
    fireEvent.keyDown(dlg, { key: 'Escape' })
    expect(denied).toBe(1)
  })

  it('Allow once approves without remembering', () => {
    const onApprove = vi.fn()
    render(<ToolApprovalPrompt tool={tool} onApprove={onApprove} onDeny={() => {}} />)
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-testid="approval-once"]')!)
    expect(onApprove).toHaveBeenCalledWith(false)
  })

  it('Remember approves with the remembered flag', () => {
    const onApprove = vi.fn()
    render(<ToolApprovalPrompt tool={tool} rememberable onApprove={onApprove} onDeny={() => {}} />)
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-testid="approval-remember"]')!)
    expect(onApprove).toHaveBeenCalledWith(true)
  })

  it('hides Remember when the tool cannot be remembered', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    expect(container.querySelector('[data-testid="approval-remember"]')).toBeNull()
  })
})

// Wave B1: the edit family shows a real unified diff instead of raw JSON.
const REAL_DIFF = [
  '--- a/hello.txt',
  '+++ b/hello.txt',
  '@@ -1,2 +1,2 @@',
  ' alpha beta',
  '-gamma',
  '+GAMMA',
].join('\n')

describe('ToolApprovalPrompt (Wave B1: diff instead of JSON)', () => {
  const editTool = {
    id: 'e1',
    name: 'edit_file',
    args: { path: 'hello.txt', old_string: 'gamma', new_string: 'GAMMA' },
    status: 'waiting' as const,
    approval_diff: REAL_DIFF,
  }

  it('renders the unified diff (hunk + -/+) when approval_diff is present', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={editTool} onApprove={() => {}} onDeny={() => {}} />,
    )
    expect(container.querySelector('[data-testid="approval-diff"]')).not.toBeNull()
    // DiffView parses the hunk → data-testid hunk-0 + the changed line visible
    expect(container.querySelector('[data-testid="hunk-0"]')).not.toBeNull()
    expect(container.textContent).toContain('GAMMA')
  })

  it('does NOT show the raw JSON args blob when a diff is present', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={editTool} onApprove={() => {}} onDeny={() => {}} />,
    )
    // The JSON preview would contain '"old_string"' — not allowed in the diff branch.
    expect(container.textContent).not.toContain('"old_string"')
  })

  it('falls back to the args preview without approval_diff (run_shell)', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    expect(container.querySelector('[data-testid="approval-diff"]')).toBeNull()
    // run_shell args visible as a JSON line
    expect(container.textContent).toContain('ls')
  })
})

// The blast-radius label is user-facing text, so it comes from the bundle
// (chat.toolApproval.blastRadius) instead of a literal in the component. The mock
// answers that key with an English marker, so a hardcoded label fails here.
describe('ToolApprovalPrompt (blast-radius label comes from i18n)', () => {
  it('renders the blast label through chat.toolApproval.blastRadius', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const row = container.querySelector('[data-testid="approval-blast-radius"]')
    expect(row).not.toBeNull()
    expect(row!.textContent).toContain('Blast radius:')
    // the affected value stays the raw one, next to the translated label
    expect(row!.textContent).toContain('command=ls')
  })
  it('refuses and sends the correction the reader typed (E2)', () => {
    const onDeny = vi.fn()
    const onDenyWithCorrection = vi.fn()
    render(
      <ToolApprovalPrompt
        tool={tool}
        onApprove={() => {}}
        onDeny={onDeny}
        onDenyWithCorrection={onDenyWithCorrection}
      />,
    )
    fireEvent.click(screen.getByTestId('approval-deny-with-correction'))
    const input = screen.getByTestId('approval-correction') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'write it to docs/ instead' } })
    fireEvent.click(screen.getByTestId('approval-correction-send'))
    expect(onDenyWithCorrection).toHaveBeenCalledWith('write it to docs/ instead')
    expect(onDeny).not.toHaveBeenCalled()
  })

  it('keeps the send disabled until the correction has text', () => {
    render(
      <ToolApprovalPrompt
        tool={tool}
        onApprove={() => {}}
        onDeny={() => {}}
        onDenyWithCorrection={() => {}}
      />,
    )
    fireEvent.click(screen.getByTestId('approval-deny-with-correction'))
    expect((screen.getByTestId('approval-correction-send') as HTMLButtonElement).disabled).toBe(
      true,
    )
  })
})

// Finding 40: an answered gate has to look answered. The card in the audit stayed a
// live dialog after its token was spent, so what a reader of a closed gate must not be
// able to do is press something, and read a hand that was not in the room.
describe('ToolApprovalPrompt (a closed gate is closed)', () => {
  const gated = (
    approval: Partial<NonNullable<ToolCall['approval']>> = {},
    status: ToolCall['status'] = 'waiting',
  ): ToolCall => ({
    id: 'g1',
    name: 'run_shell',
    args: { command: 'ls' },
    status,
    approval: {
      token: 'tok-1',
      openedAt: Date.now(),
      state: 'waiting',
      ...approval,
    },
  })

  const actionTestIds = ['approval-once', 'approval-remember', 'approval-deny']

  it('offers nothing and names the hand on an answered gate', () => {
    const { container } = render(
      <ToolApprovalPrompt
        tool={gated({ state: 'answered', outcome: 'allowed', closedBy: 'you' }, 'approved')}
        onApprove={() => {}}
        onDeny={() => {}}
        rememberable
      />,
    )
    for (const id of actionTestIds) {
      expect(container.querySelector(`[data-testid="${id}"]`)).toBeNull()
    }
    expect(container.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'Allowed — by you',
    )
    expect(container.querySelector('[role="alertdialog"]')).toBeNull()
  })

  it('says the companion answered when the companion answered', () => {
    const { container } = render(
      <ToolApprovalPrompt
        tool={gated({ state: 'answered', outcome: 'allowed', closedBy: 'companion' }, 'approved')}
        onApprove={() => {}}
        onDeny={() => {}}
      />,
    )
    expect(container.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'Allowed — by the companion after its countdown',
    )
  })

  it('names no hand when the window closed with no decision', () => {
    const { container } = render(
      <ToolApprovalPrompt
        tool={gated({ state: 'expired', closedBy: 'server' }, 'expired')}
        onApprove={() => {}}
        onDeny={() => {}}
      />,
    )
    expect(container.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'Nobody answered before the approval window closed. Nothing ran.',
    )
    expect(container.textContent).not.toMatch(/by you|by the companion/)
    expect(container.querySelector('[data-testid="approval-deny-with-correction"]')).toBeNull()
  })

  it('calls a spent token spent instead of inventing a decision', () => {
    const { container } = render(
      <ToolApprovalPrompt
        tool={gated({ state: 'answered', closedBy: 'server' }, 'expired')}
        onApprove={() => {}}
        onDeny={() => {}}
      />,
    )
    expect(container.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'The server does not hold this approval any more — it was answered elsewhere, or the run moved on.',
    )
    expect(container.textContent).not.toMatch(/by you|by the companion/)
  })

  it('leaves an answer in flight visibly in flight, with nothing left to press', () => {
    const { container } = render(
      <ToolApprovalPrompt
        tool={gated({ state: 'submitting' })}
        rememberable
        onApprove={() => {}}
        onDeny={() => {}}
      />,
    )
    expect(container.querySelector('[data-testid="approval-sending"]')?.textContent).toBe(
      'Sending your answer…',
    )
    for (const id of actionTestIds) {
      expect((container.querySelector(`[data-testid="${id}"]`) as HTMLButtonElement).disabled).toBe(
        true,
      )
    }
  })

  it('takes neither the dialog role nor the focus when it is not the gate being asked', () => {
    const onDeny = vi.fn()
    const { container } = render(
      <>
        <ToolApprovalPrompt tool={gated()} onApprove={() => {}} onDeny={onDeny} />
        <ToolApprovalPrompt
          tool={gated({ token: 'tok-2' })}
          primary={false}
          onApprove={() => {}}
          onDeny={onDeny}
        />
      </>,
    )
    expect(container.querySelectorAll('[role="alertdialog"]')).toHaveLength(1)
    const second = container.querySelectorAll('[data-testid="approval-card"]')[1]!
    expect(second.getAttribute('role')).toBe('group')
    expect(second.contains(document.activeElement)).toBe(false)
    // Its keys are ordinary keys: nothing in a card behind the ask refuses a run.
    fireEvent.keyDown(second, { key: 'Escape' })
    expect(onDeny).not.toHaveBeenCalled()
  })

  it('refuses the keys of a closed card', () => {
    const onDeny = vi.fn()
    const { container } = render(
      <ToolApprovalPrompt
        tool={gated({ state: 'answered', outcome: 'denied', closedBy: 'you' }, 'denied')}
        onApprove={() => {}}
        onDeny={onDeny}
      />,
    )
    fireEvent.keyDown(container, { key: 'Escape' })
    expect(onDeny).not.toHaveBeenCalled()
    expect(container.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'Refused — by you',
    )
  })
})
