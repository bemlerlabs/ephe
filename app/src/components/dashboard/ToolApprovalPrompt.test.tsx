import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import ToolApprovalPrompt from '@/components/dashboard/ToolApprovalPrompt'

// i18n mock (ToolApprovalPrompt uses useTranslation)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'chat.approvalNeeded': 'Bestätigung erforderlich',
        'chat.toolApproval.approve': 'Genehmigen',
        'chat.toolApproval.deny': 'Ablehnen',
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
  it('hat role=alertdialog mit aria-label', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const dlg = container.querySelector('[role="alertdialog"]')
    expect(dlg).not.toBeNull()
    expect(dlg!.getAttribute('aria-label')).toContain('Bestätigung')
  })

  it('setzt initial den Fokus auf den Ablehnen-Button (konservativ: deny zuerst)', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const deny = container.querySelector<HTMLButtonElement>('[aria-label="Ablehnen"]')
    expect(deny?.contains(document.activeElement) || document.activeElement === deny).toBe(true)
  })

  it('Focus-Trap: Tab-Zyklus bleibt innerhalb des Dialogs (Approve → Deny → Approve)', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => {}} />,
    )
    const dlg = container.querySelector('[role="alertdialog"]')!
    const approve = container.querySelector<HTMLButtonElement>('[aria-label="Genehmigen"]')!
    const deny = container.querySelector<HTMLButtonElement>('[aria-label="Ablehnen"]')!

    // Start: focus sits on Deny (auto-focus)
    deny.focus()

    // Tab from Deny → Approve (wrap)
    fireEvent.keyDown(deny, { key: 'Tab' })
    expect(dlg.contains(document.activeElement)).toBe(true)

    // Shift+Tab from Approve → Deny (wrap back)
    approve.focus()
    fireEvent.keyDown(approve, { key: 'Tab', shiftKey: true })
    expect(dlg.contains(document.activeElement)).toBe(true)
  })

  it('Esc löst onDeny aus (Flucht-Pfad)', () => {
    let denied = 0
    const { container } = render(
      <ToolApprovalPrompt tool={tool} onApprove={() => {}} onDeny={() => denied++} />,
    )
    const dlg = container.querySelector('[role="alertdialog"]')!
    fireEvent.keyDown(dlg, { key: 'Escape' })
    expect(denied).toBe(1)
  })

  it('onApprove wird beim Klick auf Genehmigen aufgerufen', () => {
    let approved = 0
    render(<ToolApprovalPrompt tool={tool} onApprove={() => approved++} onDeny={() => {}} />)
    const approve = document.querySelector<HTMLButtonElement>('[aria-label="Genehmigen"]')!
    fireEvent.click(approve)
    expect(approved).toBe(1)
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

describe('ToolApprovalPrompt (Wave B1: Diff statt JSON)', () => {
  const editTool = {
    id: 'e1',
    name: 'edit_file',
    args: { path: 'hello.txt', old_string: 'gamma', new_string: 'GAMMA' },
    status: 'waiting' as const,
    approval_diff: REAL_DIFF,
  }

  it('rendert den Unified-Diff (Hunk + -/+) wenn approval_diff vorhanden', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={editTool} onApprove={() => {}} onDeny={() => {}} />,
    )
    expect(container.querySelector('[data-testid="approval-diff"]')).not.toBeNull()
    // DiffView parses the hunk → data-testid hunk-0 + the changed line visible
    expect(container.querySelector('[data-testid="hunk-0"]')).not.toBeNull()
    expect(container.textContent).toContain('GAMMA')
  })

  it('zeigt NICHT den Raw-JSON-Args-Blob, wenn ein Diff vorhanden ist', () => {
    const { container } = render(
      <ToolApprovalPrompt tool={editTool} onApprove={() => {}} onDeny={() => {}} />,
    )
    // The JSON preview would contain '"old_string"' — not allowed in the diff branch.
    expect(container.textContent).not.toContain('"old_string"')
  })

  it('fällt ohne approval_diff auf die Args-Vorschau zurück (run_shell)', () => {
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
