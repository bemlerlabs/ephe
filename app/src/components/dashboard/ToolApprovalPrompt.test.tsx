import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import ToolApprovalPrompt from '@/components/dashboard/ToolApprovalPrompt'

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
    const remember = container.querySelector<HTMLButtonElement>('[data-testid="approval-remember"]')!
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
})
