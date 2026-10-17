import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReviewTab } from '@/components/dashboard/AgentPanel'
import { gitStatus, gitDiff, gitAdd, gitCommit } from '@/lib/api'

// W3c (2026-09-09): Git tab buttons — Stage all + Commit from the Review tab.
// Fed by the POST routes /api/git/add + /api/git/commit (argument-list pattern).

vi.mock('@/lib/api', () => ({
  gitStatus: vi.fn(),
  gitDiff: vi.fn(),
  gitAdd: vi.fn(),
  gitCommit: vi.fn(),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/proj' })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

import type { GitFileChange } from '@/lib/api'

const CHANGES: GitFileChange[] = [{ path: 'src/app.py', status: 'M', additions: 12, deletions: 3 }]

describe('ReviewTab Git-Aktionen (W3c)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(gitStatus).mockResolvedValue({
      workspace: 'proj',
      git: true,
      branch: 'main',
      changes: CHANGES,
    })
    vi.mocked(gitDiff).mockResolvedValue({ path: 'src/app.py', diff: '@@ x @@', binary: false })
    vi.mocked(gitAdd).mockResolvedValue({ ok: true, staged: 1 })
    vi.mocked(gitCommit).mockResolvedValue({ ok: true, hash: 'deadbeefcafe1234', branch: 'main' })
  })

  it('Klick auf Stage all ruft gitAdd ohne Pfadliste (Arbeitsbaum -A)', async () => {
    render(<ReviewTab />)
    await screen.findByText('src/app.py')
    fireEvent.click(screen.getByTestId('git-stage-all'))
    await waitFor(() => expect(gitAdd).toHaveBeenCalled())
  })

  it('Commit-Button ist bei leerer Nachricht deaktiviert, nach Eingabe aktiv mit Text', async () => {
    render(<ReviewTab />)
    const btn = await screen.findByTestId('git-commit')
    expect((btn as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByTestId('git-commit-msg'), { target: { value: 'feat: x' } })
    await waitFor(() =>
      expect((screen.getByTestId('git-commit') as HTMLButtonElement).disabled).toBe(false),
    )
  })

  it('Commit mit Nachricht ruft gitCommit und zeigt Bestaetigungs-Meldung', async () => {
    render(<ReviewTab />)
    fireEvent.change(await screen.findByTestId('git-commit-msg'), { target: { value: 'feat: y' } })
    fireEvent.click(screen.getByTestId('git-commit'))
    await waitFor(() => expect(gitCommit).toHaveBeenCalledWith('feat: y'))
    expect(await screen.findByText('agentPanel.gitCommitted')).toBeTruthy()
  })
})
