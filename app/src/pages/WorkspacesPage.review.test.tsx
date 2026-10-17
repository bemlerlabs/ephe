/**
 * W1 — the review half, driven through the page a reviewer actually stands on.
 *
 * The rule these tests hold is the task's own: a refused action reaches the reader as a
 * sentence. So each refusal case asserts on the words, and one of them asserts the
 * absence of the transport status outright — "409" is exactly what must not be shown.
 *
 * The payload shape is pinned too, because it is a contract with the route sibling:
 * `{verdict, reviewer, reasons:[{path, line, why}]}`, and `publish` is asked to check
 * before it publishes unless the reviewer unchecked that.
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

/** Open the review form of the one change set on the page. */
async function openReview() {
  renderPage()
  fireEvent.click(await screen.findByTestId('changeset-review-open-cs-w1-1'))
  return screen.findByTestId('review-form-cs-w1-1')
}

function nameReviewer(value: string) {
  fireEvent.change(screen.getByLabelText('workspaces.review.reviewer'), { target: { value } })
}

function giveReason(why: string) {
  fireEvent.change(screen.getByLabelText('workspaces.review.why'), { target: { value: why } })
}

describe('filing a verdict', () => {
  it('opens on request and stays closed until then', async () => {
    renderPage()
    await screen.findByTestId('changeset-card-cs-w1-1')
    expect(screen.queryByTestId('review-form-cs-w1-1')).toBeNull()
    fireEvent.click(screen.getByTestId('changeset-review-open-cs-w1-1'))
    expect(await screen.findByTestId('review-form-cs-w1-1')).toBeTruthy()
  })

  it('sends the verdict, the reviewer and a located reason', async () => {
    api.reviewChangeSet.mockResolvedValue({
      verdict: {
        change_set_id: 'cs-w1-1',
        verdict: 'approve',
        reviewer: 'reviewer-a',
        reasons: [],
      },
    })
    await openReview()
    nameReviewer('reviewer-a')
    giveReason('reads well')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-approve'))

    await waitFor(() =>
      expect(api.reviewChangeSet).toHaveBeenCalledWith('cs-w1-1', {
        verdict: 'approve',
        reviewer: 'reviewer-a',
        reasons: [{ path: 'app/src/pages/WorkspacesPage.tsx', line: 1, why: 'reads well' }],
      }),
    )
  })

  it('prefills the reason with a file the change set really touches', async () => {
    await openReview()
    const path = screen.getByLabelText('workspaces.review.path') as HTMLSelectElement
    expect(path.value).toBe('app/src/pages/WorkspacesPage.tsx')
  })

  it('answers with a sentence naming who decided', async () => {
    api.reviewChangeSet.mockResolvedValue({
      verdict: {
        change_set_id: 'cs-w1-1',
        verdict: 'approve',
        reviewer: 'reviewer-a',
        reasons: [],
      },
    })
    await openReview()
    nameReviewer('reviewer-a')
    giveReason('reads well')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-approve'))
    const sentence = await screen.findByTestId('review-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('workspaces.review.done.approve')
    expect(sentence.dataset.tone).toBe('ok')
  })

  it('keeps the sentence on screen by re-reading only that workspace', async () => {
    // The bug this guards: a verdict used to refresh the whole register, which blanked the
    // page and unmounted the pane — so the reviewer's confirmation vanished the moment it
    // appeared. Only the one workspace may be read again.
    api.reviewChangeSet.mockResolvedValue({
      verdict: { verdict: 'approve', reviewer: 'reviewer-a' },
    })
    await openReview()
    nameReviewer('reviewer-a')
    giveReason('reads well')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-approve'))
    await screen.findByTestId('review-sentence-cs-w1-1')
    await waitFor(() => expect(api.listChangeSets).toHaveBeenCalledTimes(2))
    expect(api.listWorkspaces).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('review-form-cs-w1-1')).toBeTruthy()
    expect(screen.getByTestId('review-sentence-cs-w1-1').textContent).toContain(
      'workspaces.review.done.approve',
    )
  })

  it('sends the other two verdicts by their own names', async () => {
    api.reviewChangeSet.mockResolvedValue({
      verdict: { verdict: 'reject', reviewer: 'reviewer-a' },
    })
    await openReview()
    nameReviewer('reviewer-a')
    giveReason('wrong layer')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-reject'))
    await waitFor(() =>
      expect(api.reviewChangeSet).toHaveBeenCalledWith(
        'cs-w1-1',
        expect.objectContaining({ verdict: 'reject' }),
      ),
    )
  })

  it('does not ask the server for a verdict without a reason', async () => {
    await openReview()
    nameReviewer('reviewer-a')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-approve'))
    const sentence = await screen.findByTestId('review-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('workspaces.review.needReason')
    expect(api.reviewChangeSet).not.toHaveBeenCalled()
  })

  it('does not ask the server for a verdict without a reviewer', async () => {
    await openReview()
    giveReason('reads well')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-reject'))
    expect((await screen.findByTestId('review-sentence-cs-w1-1')).textContent).toContain(
      'workspaces.review.needReason',
    )
    expect(api.reviewChangeSet).not.toHaveBeenCalled()
  })

  it('warns before an author tries to approve their own work', async () => {
    await openReview()
    nameReviewer('w1-ui')
    expect((await screen.findByTestId('review-author-cs-w1-1')).textContent).toContain(
      'workspaces.review.authorWarn',
    )
  })
})

describe('a refused review reads as a sentence', () => {
  it('carries the sentence the gate refused with, and never the status', async () => {
    const refused =
      'w1-ui authored cs-w1-1 and cannot approve it — an approval has to come from somebody else'
    api.reviewChangeSet.mockRejectedValue(new api.ApiError(refused, 422, ''))
    await openReview()
    nameReviewer('w1-ui')
    giveReason('my own work')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-approve'))

    const sentence = await screen.findByTestId('review-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('cannot approve it')
    expect(sentence.dataset.tone).toBe('warn')
    // The transport status is not an answer about the change set.
    expect(sentence.textContent).not.toContain('422')
    expect(sentence.textContent).not.toContain('HTTP')
  })

  it('prefers the reader language when the refusal carries a code', async () => {
    api.reviewChangeSet.mockRejectedValue(
      new api.ApiError('backend unreachable', 504, 'request_timeout'),
    )
    await openReview()
    nameReviewer('reviewer-a')
    giveReason('reads well')
    fireEvent.click(screen.getByTestId('review-submit-cs-w1-1-approve'))
    const sentence = await screen.findByTestId('review-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('did not answer in time')
    expect(sentence.textContent).not.toContain('request_timeout')
    expect(sentence.textContent).not.toContain('504')
  })
})

describe('publishing', () => {
  it('asks to check first, without a target it does not have', async () => {
    api.publishChangeSet.mockResolvedValue({
      result: {
        ok: true,
        applied: [],
        rolled_back: [],
        reason: 'dry run: 1 file(s) would publish to main',
      },
    })
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-publish-cs-w1-1'))
    await waitFor(() =>
      expect(api.publishChangeSet).toHaveBeenCalledWith('cs-w1-1', { dry_run: true }),
    )
    const sentence = await screen.findByTestId('changeset-publish-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('dry run: 1 file(s) would publish to main')
    expect(sentence.dataset.tone).toBe('ok')
  })

  it('really publishes once the check is unticked', async () => {
    api.publishChangeSet.mockResolvedValue({
      result: {
        ok: true,
        applied: ['app/src/pages/WorkspacesPage.tsx'],
        rolled_back: [],
        reason: 'published 1 file(s) to main',
      },
    })
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-dryrun-cs-w1-1'))
    fireEvent.click(screen.getByTestId('changeset-publish-cs-w1-1'))
    await waitFor(() =>
      expect(api.publishChangeSet).toHaveBeenCalledWith('cs-w1-1', { dry_run: false }),
    )
    expect((await screen.findByTestId('changeset-publish-sentence-cs-w1-1')).textContent).toContain(
      'published 1 file(s) to main',
    )
  })

  it('reads a rolled-back publish as its own sentence, not as a status', async () => {
    api.publishChangeSet.mockResolvedValue({
      result: {
        ok: false,
        applied: [],
        rolled_back: ['app/src/pages/WorkspacesPage.tsx'],
        reason: 'aborted before publish: the tree was already moved',
      },
    })
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-publish-cs-w1-1'))
    const sentence = await screen.findByTestId('changeset-publish-sentence-cs-w1-1')
    expect(sentence.textContent).toContain('aborted before publish: the tree was already moved')
    expect(sentence.dataset.tone).toBe('warn')
  })

  it('carries the 409 sentence the route refused with, not the 409', async () => {
    api.publishChangeSet.mockRejectedValue(
      new api.ApiError(
        "change set 'cs-w1-1' carries no approval from a reviewer other than its author",
        409,
        '',
      ),
    )
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-publish-cs-w1-1'))
    const sentence = await screen.findByTestId('changeset-publish-sentence-cs-w1-1')
    expect(sentence.textContent).toContain(
      'carries no approval from a reviewer other than its author',
    )
    expect(sentence.textContent).not.toContain('409')
  })
})
