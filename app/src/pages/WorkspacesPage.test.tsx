/**
 * W1 — the workspaces page has to read at three sizes, so all three are built here:
 * nothing registered, one live workspace, and twenty. The tests are written against the
 * three states themselves rather than against the markup, because the failure they guard
 * against is one state silently borrowing another's face — an empty register shown as an
 * error, or twenty rows and no way to narrow them.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
  }
})

const api = vi.hoisted(() => {
  /** The real class's contract, kept here so `instanceof ApiError` in the surface under
   * test still answers — the same three lines the API module ships. */
  class ApiError extends Error {
    readonly status: number
    readonly reasonCode: string
    constructor(message: string, status: number, reasonCode = '') {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.reasonCode = reasonCode
    }
  }
  return {
    ApiError,
    listWorkspaces: vi.fn(),
    listChangeSets: vi.fn(),
    reviewChangeSet: vi.fn(),
    publishChangeSet: vi.fn(),
    getChangeSetLifecycle: vi.fn(),
    amendChangeSet: vi.fn(),
    moveChangeSetState: vi.fn(),
  }
})

vi.mock('@/lib/api', () => api)

import WorkspacesPage from './WorkspacesPage'

interface Row {
  id: string
  path: string
  branch: string
  state: string
  owner: string
  created_at: string
}

function workspace(n: number, over: Partial<Row> = {}): Row {
  return {
    id: `w${n}`,
    path: `/work/ephe-wt/w${n}`,
    branch: `wt/w${n}`,
    state: 'ready',
    owner: `agent-${n}`,
    created_at: new Date(Date.now() - n * 60_000).toISOString(),
    ...over,
  }
}

function changeSet(ws: string, n: number, path = `app/src/file-${ws}-${n}.tsx`) {
  return {
    id: `cs-${ws}-${n}`,
    workspace_id: ws,
    summary: `Change ${n} in ${ws}`,
    files: [
      { path, op: 'modify', diff_sha: `sha256:${'ab'.repeat(20)}${n}` },
      {
        path: `app/src/new-${ws}-${n}.ts`,
        op: 'create',
        diff_sha: `sha256:${'cd'.repeat(20)}${n}`,
      },
    ],
    provenance: {
      session_id: `sess-${ws}-${n}`,
      agent_id: `agent-${ws}`,
      why: 'because it had to',
    },
    state: 'draft',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listChangeSets.mockResolvedValue({ change_sets: [] })
})

afterEach(cleanup)

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/workspaces']}>
      <Routes>
        <Route path="/workspaces" element={<WorkspacesPage />} />
      </Routes>
    </MemoryRouter>,
  )

describe('no workspace is registered', () => {
  beforeEach(() => api.listWorkspaces.mockResolvedValue({ workspaces: [] }))

  it('says what a workspace is instead of showing an error', async () => {
    renderPage()
    const empty = await screen.findByTestId('workspaces-empty')
    expect(empty.textContent).toContain('workspaces.emptyTitle')
    expect(empty.textContent).toContain('workspaces.emptyBody')
    // The two faces that must never stand in for this one.
    expect(screen.queryByTestId('workspaces-error')).toBeNull()
    expect(screen.queryByTestId('workspaces-list')).toBeNull()
  })

  it('asks nobody for change sets it has no workspace for', async () => {
    renderPage()
    await screen.findByTestId('workspaces-empty')
    expect(api.listChangeSets).not.toHaveBeenCalled()
  })

  it('carries a way out and no counting header', async () => {
    renderPage()
    await screen.findByTestId('workspaces-empty')
    expect(screen.getByTestId('workspaces-empty-action')).toBeTruthy()
    expect(screen.queryByTestId('workspaces-count')).toBeNull()
  })
})

describe('one live workspace', () => {
  beforeEach(() => {
    api.listWorkspaces.mockResolvedValue({ workspaces: [workspace(1)] })
    api.listChangeSets.mockResolvedValue({ change_sets: [changeSet('w1', 1)] })
  })

  it('shows the row beside its change sets', async () => {
    renderPage()
    expect(await screen.findByTestId('workspace-row-w1')).toBeTruthy()
    expect(await screen.findByTestId('changeset-card-cs-w1-1')).toBeTruthy()
    expect(screen.queryByTestId('workspaces-empty')).toBeNull()
  })

  it('names the owner, the state and the age on the row', async () => {
    renderPage()
    const row = await screen.findByTestId('workspace-row-w1')
    expect(row.textContent).toContain('agent-1')
    expect(row.textContent).toContain('workspaces.state.ready')
    expect(row.textContent).toContain('workspaces.age.')
  })

  it('carries no filter chrome for a single row', async () => {
    renderPage()
    await screen.findByTestId('workspace-row-w1')
    expect(screen.queryByTestId('workspaces-filter')).toBeNull()
  })

  it('reads every file with its operation and its diff digest', async () => {
    renderPage()
    const files = await screen.findByTestId('changeset-files-cs-w1-1')
    expect(files.textContent).toContain('app/src/file-w1-1.tsx')
    expect(files.textContent).toContain('workspaces.op.modify')
    expect(files.textContent).toContain('workspaces.op.create')
    // The digest is shortened to the head a reviewer can compare by eye.
    expect(files.textContent).toContain('sha256:abababab')
    expect(files.textContent).not.toContain('sha256:abababababababababababababababababababab')
  })

  it('reads the provenance, because that is the part a session drops', async () => {
    renderPage()
    const prov = await screen.findByTestId('changeset-provenance-cs-w1-1')
    expect(prov.textContent).toContain('because it had to')
  })
})

describe('twenty live workspaces', () => {
  const rows = Array.from({ length: 20 }, (_, i) => workspace(i + 1))

  beforeEach(() => {
    api.listWorkspaces.mockResolvedValue({ workspaces: rows })
    api.listChangeSets.mockImplementation(async (id: string) => ({
      change_sets: [changeSet(id, 1)],
    }))
  })

  it('lists all twenty and counts them in the header', async () => {
    renderPage()
    await waitFor(() => expect(screen.getAllByTestId(/^workspace-row-w/)).toHaveLength(20))
    expect(screen.getByTestId('workspaces-count').textContent).toContain('workspaces.count')
  })

  it('reads them in parallel rather than one after the other', async () => {
    renderPage()
    await waitFor(() => expect(api.listChangeSets).toHaveBeenCalledTimes(20))
  })

  it('offers the filter from the second row on and narrows to one', async () => {
    renderPage()
    const filter = await screen.findByTestId('workspaces-filter')
    fireEvent.change(filter, { target: { value: 'agent-7' } })
    await waitFor(() => expect(screen.getAllByTestId(/^workspace-row-w/)).toHaveLength(1))
    // The pane follows the visible list, so the filtered row is the one on the right.
    expect(screen.getByTestId('workspace-detail').textContent).toContain('agent-7')
  })

  it('says so when the filter matches nothing, and offers the way back', async () => {
    renderPage()
    const filter = await screen.findByTestId('workspaces-filter')
    fireEvent.change(filter, { target: { value: 'no-such-agent' } })
    const nomatch = await screen.findByTestId('workspaces-nomatch')
    expect(nomatch.textContent).toContain('workspaces.nomatchHidden')
    fireEvent.click(screen.getByTestId('workspaces-clear-filter'))
    await waitFor(() => expect(screen.getAllByTestId(/^workspace-row-w/)).toHaveLength(20))
    expect(screen.queryByTestId('workspaces-nomatch')).toBeNull()
  })

  it('names the paths two workspaces are changing at the same time', async () => {
    const shared = 'app/src/shared.ts'
    api.listChangeSets.mockImplementation(async (id: string) => ({
      change_sets: [changeSet(id, 1, id === 'w1' || id === 'w2' ? shared : `app/src/${id}.ts`)],
    }))
    renderPage()
    const strip = await screen.findByTestId('workspaces-conflicts')
    expect(strip.textContent).toContain(shared)
    expect(strip.textContent).toContain('agent-1')
    expect(strip.textContent).toContain('agent-2')
  })

  it('keeps a page-wide silence when no two workspaces collide', async () => {
    renderPage()
    await waitFor(() => expect(api.listChangeSets).toHaveBeenCalledTimes(20))
    expect(screen.queryByTestId('workspaces-conflicts')).toBeNull()
  })

  it('tells the run itself on its own card, where the collision is still a decision', async () => {
    const shared = 'app/src/shared.ts'
    api.listChangeSets.mockImplementation(async (id: string) => ({
      change_sets: [changeSet(id, 1, id === 'w1' || id === 'w2' ? shared : `app/src/${id}.ts`)],
    }))
    renderPage()

    // The strip names the path; the card that owns the set names the *other run* on it — the
    // same reading in the surface a run actually stands in, not only in a page-wide banner.
    const card = await screen.findByTestId('changeset-conflict-cs-w1-1')
    expect(card.textContent).toContain('workspaces.conflictWarning')
    expect(card.textContent).toContain(shared)
    expect(card.textContent).toContain('agent-2')
    expect(card.textContent).not.toContain('agent-1') // the set does not warn about itself
  })

  it('leaves a card silent when no other run shares its paths', async () => {
    renderPage()
    await waitFor(() => expect(api.listChangeSets).toHaveBeenCalledTimes(20))
    expect(screen.queryByTestId(/^changeset-conflict-/)).toBeNull()
  })
})

describe('reads that fail', () => {
  it('shows a refusal for the page only when the register itself is unreadable', async () => {
    api.listWorkspaces.mockRejectedValue(new Error('connect ECONNREFUSED 127.0.0.1:8777'))
    renderPage()
    const error = await screen.findByTestId('workspaces-error')
    expect(error.textContent).toContain('workspaces.failed')
    expect((await screen.findByTestId('workspaces-error-reason')).textContent).toContain(
      'ECONNREFUSED',
    )
    expect(screen.queryByTestId('workspaces-empty')).toBeNull()
  })

  it('brings the register back on one retry press', async () => {
    api.listWorkspaces.mockRejectedValueOnce(new Error('gone'))
    renderPage()
    const retry = await screen.findByTestId('workspaces-retry')
    api.listWorkspaces.mockResolvedValue({ workspaces: [workspace(1)] })
    api.listChangeSets.mockResolvedValue({ change_sets: [] })
    fireEvent.click(retry)
    expect(await screen.findByTestId('workspace-row-w1')).toBeTruthy()
    expect(screen.queryByTestId('workspaces-error')).toBeNull()
  })

  it('costs one pane, not the page, when a single workspace cannot be read', async () => {
    api.listWorkspaces.mockResolvedValue({ workspaces: [workspace(1), workspace(2)] })
    api.listChangeSets.mockImplementation(async (id: string) => {
      if (id === 'w1') throw new Error('the register has no tree w1')
      return { change_sets: [] }
    })
    renderPage()
    // Both rows are still there — one unreachable workspace does not empty the overview.
    await waitFor(() => expect(screen.getAllByTestId(/^workspace-row-w/)).toHaveLength(2))
    const pane = await screen.findByTestId('changesets-error')
    expect(pane.textContent).toContain('workspaces.changeSetsFailed')
    expect((await screen.findByTestId('changesets-error-reason')).textContent).toContain(
      'no tree w1',
    )
  })
})
