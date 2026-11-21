/**
 * W1 / n1-publish — the life of a change set, driven through the page a reviewer stands on.
 *
 * `WorkspacesPage.review.test.tsx` holds the verdict-and-publish half of the surface. This file
 * holds the life half: where a set stands on the draft → review → approved → published line, the
 * located reasons behind the verdict that last moved it, the amend that re-reads the tree under
 * the same id, and the one move a surface makes by hand — reopening a set as a draft. The two
 * files share the page-level scaffolding below, which is why it is repeated here.
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

const WORKSPACE = {
  id: 'w1',
  path: '/work/ephe-wt/w1-ui',
  branch: 'wt/w1-ui',
  state: 'dirty',
  owner: 'w1-ui',
  created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
}

const CHANGE_SET = {
  id: 'cs-w1-1',
  workspace_id: 'w1',
  summary: 'The workspaces page',
  files: [
    {
      path: 'app/src/pages/WorkspacesPage.tsx',
      op: 'create',
      diff_sha: `sha256:${'9f'.repeat(32)}`,
    },
  ],
  provenance: {
    session_id: 'sess-abcdef123456',
    agent_id: 'w1-ui',
    why: 'the overview was missing',
  },
  state: 'draft',
}

/** `core/change_set_lifecycle.view` for a freshly built set, as the route hands it over. */
const LIFECYCLE = {
  change_set_id: 'cs-w1-1',
  state: 'draft',
  author: 'w1-ui',
  stations: [
    { name: 'draft', done: true, current: true },
    { name: 'review', done: false, current: false },
    { name: 'approved', done: false, current: false },
    { name: 'published', done: false, current: false },
  ],
  verdict: null,
  reasons: [],
  decidable: true,
  amendable: true,
  withdraw: [] as string[],
  can_publish: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  api.listWorkspaces.mockResolvedValue({ workspaces: [WORKSPACE] })
  api.listChangeSets.mockResolvedValue({ change_sets: [CHANGE_SET] })
  api.getChangeSetLifecycle.mockResolvedValue({ lifecycle: LIFECYCLE })
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

/**
 * Open the one card on the page, with the state the caller filed for it, and wait for the
 * node the panel draws. A life that could not be read draws a sentence in place of the
 * panel, so a caller reading that sentence names it here instead.
 */
async function openCard(state = 'draft', drawn = 'changeset-lifecycle-cs-w1-1') {
  api.listChangeSets.mockResolvedValue({ change_sets: [{ ...CHANGE_SET, state }] })
  renderPage()
  fireEvent.click(await screen.findByTestId('changeset-review-open-cs-w1-1'))
  return screen.findByTestId(drawn)
}

const STATIONS = ['draft', 'review', 'approved', 'published']

function stationNames(): (string | null)[] {
  const track = screen.getByTestId('changeset-lifecycle-track')
  return Array.from(track.querySelectorAll('[data-station]')).map((node) =>
    node.getAttribute('data-station'),
  )
}

function currentStation(): string | null {
  const track = screen.getByTestId('changeset-lifecycle-track')
  return track.querySelector('[data-current="true"]')?.getAttribute('data-station') ?? null
}

describe('the line a change set stands on', () => {
  it('draws the four stations and marks the one it stands in, without reading the life', async () => {
    renderPage()
    await screen.findByTestId('changeset-card-cs-w1-1')
    expect(stationNames()).toEqual(STATIONS)
    expect(currentStation()).toBe('draft')
    // The line comes from the state the list already carries, so a closed card costs no call.
    expect(api.getChangeSetLifecycle).not.toHaveBeenCalled()
  })

  it('holds a sent-back set on the review station and says so without opening it', async () => {
    api.listChangeSets.mockResolvedValue({ change_sets: [{ ...CHANGE_SET, state: 'review' }] })
    renderPage()
    const hint = await screen.findByTestId('changeset-sentback-cs-w1-1')
    expect(hint.textContent).toContain('workspaces.lifecycle.sentBack')
    expect(currentStation()).toBe('review')
  })

  it('offers a rejected set no verdict form, only the way back', async () => {
    api.getChangeSetLifecycle.mockResolvedValue({
      lifecycle: { ...LIFECYCLE, state: 'rejected', withdraw: ['draft'] },
    })
    await openCard('rejected')
    expect(screen.queryByTestId('review-form-cs-w1-1')).toBeNull()
    expect(screen.getByTestId('changeset-amend-cs-w1-1')).toBeTruthy()
    expect(screen.getByTestId('changeset-withdraw-draft-cs-w1-1')).toBeTruthy()
  })

  it('offers a published set no move at all, and says the set is final', async () => {
    api.getChangeSetLifecycle.mockResolvedValue({
      lifecycle: {
        ...LIFECYCLE,
        state: 'published',
        amendable: false,
        withdraw: [],
        decidable: false,
      },
    })
    await openCard('published')
    expect(screen.queryByTestId('changeset-amend-cs-w1-1')).toBeNull()
    expect(screen.getByText('workspaces.lifecycle.none')).toBeTruthy()
    expect(screen.queryByTestId('review-form-cs-w1-1')).toBeNull()
  })
})

describe('reading the life', () => {
  it('reads it when the card opens, with the reasons behind the last verdict', async () => {
    const why = 'the second line needs a reason'
    const reason = { path: 'app/src/pages/WorkspacesPage.tsx', line: 7, why }
    api.getChangeSetLifecycle.mockResolvedValue({
      lifecycle: {
        ...LIFECYCLE,
        state: 'review',
        stations: [
          { name: 'draft', done: true, current: false },
          { name: 'review', done: true, current: true },
          { name: 'approved', done: false, current: false },
          { name: 'published', done: false, current: false },
        ],
        verdict: {
          change_set_id: 'cs-w1-1',
          verdict: 'request_changes',
          reviewer: 'reviewer-a',
          reasons: [reason],
        },
        reasons: [reason],
        withdraw: ['draft'],
      },
    })
    await openCard('review')
    await waitFor(() => expect(api.getChangeSetLifecycle).toHaveBeenCalledWith('cs-w1-1'))
    const last = await screen.findByTestId('changeset-lifecycle-last-cs-w1-1')
    expect(last.textContent).toContain('workspaces.verdict.request_changes')
    expect(last.textContent).toContain('reviewer-a')
    const reasons = screen.getByTestId('changeset-lifecycle-reasons-cs-w1-1')
    expect(reasons.textContent).toContain('app/src/pages/WorkspacesPage.tsx:7')
    expect(reasons.textContent).toContain(why)
  })

  it('says a verdict has not been recorded rather than leaving the line blank', async () => {
    await openCard('draft')
    expect((await screen.findByTestId('changeset-lifecycle-last-cs-w1-1')).textContent).toContain(
      'workspaces.lifecycle.noVerdict',
    )
    expect(screen.queryByTestId('changeset-lifecycle-reasons-cs-w1-1')).toBeNull()
  })

  it('reads a life it could not load as a sentence, not as a status', async () => {
    api.getChangeSetLifecycle.mockRejectedValue(
      new api.ApiError('change set cs-w1-1 is not in the store', 404, ''),
    )
    const alert = await openCard('draft', 'changeset-lifecycle-error-cs-w1-1')
    expect(alert.textContent).toContain('workspaces.lifecycle.failed')
    expect(alert.textContent).toContain('is not in the store')
    expect(alert.textContent).not.toContain('404')
  })
})

describe('amending and reopening', () => {
  it('amends under the same id and keeps the pane, re-reading only what changed', async () => {
    api.amendChangeSet.mockResolvedValue({ change_set: { ...CHANGE_SET } })
    await openCard('draft')
    const before = api.getChangeSetLifecycle.mock.calls.length
    fireEvent.click(await screen.findByTestId('changeset-amend-cs-w1-1'))
    await waitFor(() => expect(api.amendChangeSet).toHaveBeenCalledWith('cs-w1-1'))
    expect(
      (await screen.findByTestId('changeset-lifecycle-sentence-cs-w1-1')).textContent,
    ).toContain('workspaces.amend.done')
    // The life is read again after the move, so the panel never shows a state the set left.
    await waitFor(() => expect(api.getChangeSetLifecycle.mock.calls.length).toBeGreaterThan(before))
    // And the page re-reads the one workspace, not the register — the pane stays mounted.
    await waitFor(() => expect(api.listChangeSets).toHaveBeenCalledTimes(2))
    expect(api.listWorkspaces).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('review-form-cs-w1-1')).toBeTruthy()
  })

  it('reopens a set as a draft by hand when the loop allows it', async () => {
    api.getChangeSetLifecycle.mockResolvedValue({
      lifecycle: { ...LIFECYCLE, state: 'rejected', amendable: true, withdraw: ['draft'] },
    })
    api.moveChangeSetState.mockResolvedValue({ change_set: { ...CHANGE_SET, state: 'draft' } })
    await openCard('rejected')
    fireEvent.click(await screen.findByTestId('changeset-withdraw-draft-cs-w1-1'))
    await waitFor(() => expect(api.moveChangeSetState).toHaveBeenCalledWith('cs-w1-1', 'draft'))
    expect(
      (await screen.findByTestId('changeset-lifecycle-sentence-cs-w1-1')).textContent,
    ).toContain('workspaces.withdraw.done')
  })

  it('reads a refused amend as its sentence and never as the status', async () => {
    api.amendChangeSet.mockRejectedValue(
      new api.ApiError(
        'a published change set is final — record the set again from the live tree',
        409,
        '',
      ),
    )
    await openCard('draft')
    fireEvent.click(await screen.findByTestId('changeset-amend-cs-w1-1'))
    const sentence = await screen.findByTestId('changeset-lifecycle-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('a published change set is final')
    expect(sentence.textContent).not.toContain('409')
    expect(sentence.textContent).not.toContain('HTTP')
    expect(sentence.dataset.tone).toBe('warn')
  })
})
