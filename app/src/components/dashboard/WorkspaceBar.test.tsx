/**
 * W20 — WorkspaceBar: the slim row above the composer (the reference pattern
 * from the desktop client): project chip with a portal dropdown (search, projects,
 * „Ordner öffnen…", „Work outside a project") // language-gate: ignore — „Ordner öffnen…" is the label the German UI renders (locales/de.json:1452)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import WorkspaceBar from './WorkspaceBar'
import { listFs } from '@/lib/api'

const listProjects = vi.fn()
const updateSettings = vi.fn(async () => ({}))

vi.mock('@/lib/api', () => ({
  listProjects: (...a: unknown[]) => listProjects(...(a as [])),
  updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
}))

vi.mock('./FolderPickerDialog', () => ({
  default: () => null,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

// useWorkspaceName/-Switcher live in WorkspacePicker — tested with the real
// hooks (they use listFs/updateSettings from the mocked api module).
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listProjects: (...a: unknown[]) => listProjects(...(a as [])),
    updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
    listFs: vi.fn(async () => ({
      path: '/tmp/proj',
      home: '/tmp',
      workspace: '/tmp/proj',
      workspace_set: true,
      parent: null,
      entries: [],
    })),
  }
})

beforeEach(() => {
  listProjects.mockReset().mockResolvedValue({
    workspace: '/tmp/proj',
    projects: [
      { name: 'alpha', path: '/tmp/alpha', stacks: [], score: 1 },
      { name: 'beta', path: '/tmp/beta', stacks: [], score: 2 },
    ],
    generated_at: '',
  })
  updateSettings.mockClear()
})

describe('WorkspaceBar (W20)', () => {
  it('zeigt Projekt-Chip + Branch, Dropdown mit Suche, Projekten und Aktionen', async () => {
    render(<WorkspaceBar branch="main" dirty={3} git />)
    const chip = screen.getByTestId('workspace-bar-chip')
    expect(chip).toBeTruthy()
    fireEvent.click(chip)
    expect(await screen.findByTestId('workspace-bar-menu')).toBeTruthy()
    expect(screen.getByPlaceholderText('workspaceBar.searchPlaceholder')).toBeTruthy()
    expect(screen.getByText('alpha')).toBeTruthy()
    expect(screen.getByText('workspaceBar.openFolder')).toBeTruthy()
    expect(screen.getByText('workspaceBar.workOutside')).toBeTruthy()
    // branch chip with the dirty counter:
    const branch = screen.getByTestId('workspace-bar-branch')
    expect(branch.textContent).toContain('main')
    expect(branch.textContent).toContain('3')
  })

  it('Suche filtert die Projektliste', async () => {
    render(<WorkspaceBar />)
    fireEvent.click(screen.getByTestId('workspace-bar-chip'))
    await screen.findByTestId('workspace-bar-menu')
    fireEvent.change(screen.getByPlaceholderText('workspaceBar.searchPlaceholder'), {
      target: { value: 'bet' },
    })
    expect(screen.getByText('beta')).toBeTruthy()
    expect(screen.queryByText('alpha')).toBeNull()
  })
})

describe('WorkspaceBar — 24 px floor and one glyph size (W13)', () => {
  // Measured in the live client at 1440 px before this change (2026-10-13): the
  // chip 116.1 x 21 px, glyphs 12 px + 10 px in one row; and 390 px hides the
  // whole bar (`max-sm:hidden`), so the floor below is a desktop-only read.
  it('the chip carries the floor with no width guard and two 14 px glyphs', () => {
    render(<WorkspaceBar branch="main" dirty={1} git />)
    const chip = screen.getByTestId('workspace-bar-chip')
    expect(chip.className.split(/\s+/)).toContain('min-h-6')
    const glyphs = [...chip.querySelectorAll('svg')]
    expect(glyphs).toHaveLength(2)
    for (const glyph of glyphs) {
      expect(glyph.getAttribute('class')).toContain('h-3.5')
      expect(glyph.getAttribute('class')).toContain('w-3.5')
    }
  })

  it('the branch chip matches the row height and its glyph step', () => {
    render(<WorkspaceBar branch="main" dirty={3} git />)
    const branch = screen.getByTestId('workspace-bar-branch')
    expect(branch.className.split(/\s+/)).toContain('min-h-6')
    expect(branch.querySelector('svg')!.getAttribute('class')).toContain('h-3.5 w-3.5')
  })
})

describe('WorkspaceBar — three-state chip (W4)', () => {
  // The module-level vi.mock factory owns the listFs handle; per-test
  // overrides restore the default response afterwards (no order coupling).
  const defaultFs = {
    path: '/tmp/proj',
    home: '/tmp',
    workspace: '/tmp/proj',
    workspace_set: true,
    parent: null,
    entries: [],
  }
  const listFsMock = listFs as unknown as {
    mockResolvedValue: (v: unknown) => void
    mockReset: () => void
  }

  afterEach(() => {
    listFsMock.mockReset()
    listFsMock.mockResolvedValue(defaultFs)
  })

  it('state 1 — workspace_set=true shows the project name', async () => {
    listFsMock.mockResolvedValue({ ...defaultFs, workspace: '/home/u/proj', workspace_set: true })
    render(<WorkspaceBar />)
    expect(await screen.findByText('proj')).toBeTruthy()
  })

  it('state 2 — workspace_set=false shows the neutral label even with a CWD mirror', async () => {
    listFsMock.mockResolvedValue({ ...defaultFs, workspace: '/Users/x/ephe', workspace_set: false })
    render(<WorkspaceBar />)
    expect(await screen.findByText('workspaceBar.neutralWorkspace')).toBeTruthy()
  })

  it('legacy responses without the flag count as neutral (strict contract)', async () => {
    const { workspace_set: _drop, ...legacy } = defaultFs
    listFsMock.mockResolvedValue(legacy)
    render(<WorkspaceBar />)
    expect(await screen.findByText('workspaceBar.neutralWorkspace')).toBeTruthy()
  })
})
