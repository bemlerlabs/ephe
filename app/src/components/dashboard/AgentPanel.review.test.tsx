import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReviewTab } from '@/components/dashboard/AgentPanel'
import { gitStatus, gitDiff } from '@/lib/api'

// Runden-G (2026-09-07): the Git tab is a real review tab, like the reference —
// file list of workspace changes (+N/−M chips), expandable patches, refresh,
// staged/working-copy toggle. Fed from the new read-only routes
// /api/git/status + /api/git/diff.

vi.mock('@/lib/api', () => ({
  gitStatus: vi.fn(),
  gitDiff: vi.fn(),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/proj' })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

import type { GitFileChange } from '@/lib/api'

const CHANGES: GitFileChange[] = [
  { path: 'src/app.py', status: 'M', additions: 12, deletions: 3 },
  { path: 'docs/neu.md', status: '?', additions: 40, deletions: 0 },
  { path: 'alt.txt', status: 'D', additions: 0, deletions: 9 },
]

describe('ReviewTab (Runden-G, Referenz-Paritaet)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(gitStatus).mockResolvedValue({
      workspace: 'proj',
      git: true,
      branch: 'main',
      changes: CHANGES,
    })
    vi.mocked(gitDiff).mockResolvedValue({
      path: 'src/app.py',
      diff: '@@ -1,2 +1,3 @@\n alt\n-weg\n+neu\n+zeile',
      binary: false,
    })
  })

  it('laedt die Aenderungsliste beim Mount mit Pfad, Status-Kurzcode und +N/−M-Chips', async () => {
    render(<ReviewTab />)
    expect(await screen.findByText('src/app.py')).toBeTruthy()
    expect(screen.getByText('+12')).toBeTruthy()
    expect(screen.getByText('−3')).toBeTruthy()
    expect(screen.getByTestId('review-status-chip-src/app.py').textContent).toBe('M')
    expect(screen.getByTestId('review-status-chip-docs/neu.md').textContent).toBe('?')
    expect(screen.getByTestId('review-status-chip-alt.txt').textContent).toBe('D')
    expect(gitStatus).toHaveBeenCalledWith(false)
  })

  it('Klick auf eine Zeile laedt den Patch und zeigt ihn eingeklappt in DiffView-Farbgebung', async () => {
    render(<ReviewTab />)
    fireEvent.click(await screen.findByTestId('review-row-src/app.py'))
    await waitFor(() => expect(gitDiff).toHaveBeenCalledWith('src/app.py', false))
    expect(await screen.findByText((_c, el) => el?.textContent === '+neu')).toBeTruthy()
  })

  it('Staged-Umschalter fragt die Index-Sicht ab (staged=true)', async () => {
    render(<ReviewTab />)
    await screen.findByText('src/app.py')
    fireEvent.click(screen.getByTestId('review-staged-toggle'))
    await waitFor(() => expect(gitStatus).toHaveBeenCalledWith(true))
  })

  it('Refresh-Knopf laedt die Liste neu', async () => {
    render(<ReviewTab />)
    await screen.findByText('src/app.py')
    fireEvent.click(screen.getByTestId('review-refresh'))
    await waitFor(() => expect(gitStatus).toHaveBeenCalledTimes(2))
  })

  it('keine Aenderungen -> sauberer Leerzustand (kein Zeilen-Rest)', async () => {
    vi.mocked(gitStatus).mockResolvedValue({
      workspace: 'proj',
      git: true,
      branch: 'main',
      changes: [],
    })
    render(<ReviewTab />)
    expect(await screen.findByText('agentPanel.reviewClean')).toBeTruthy()
    expect(screen.queryByText('src/app.py')).toBeNull()
  })

  it('kein Git-Repo -> ehrlicher Hinweis statt Fehler', async () => {
    vi.mocked(gitStatus).mockResolvedValue({
      workspace: 'proj',
      git: false,
      branch: '',
      changes: [],
    })
    render(<ReviewTab />)
    expect(await screen.findByText('agentPanel.gitEmpty')).toBeTruthy()
  })
})
