/**
 * W1 — the chain of custody, driven through the page a reviewer actually stands on.
 *
 * The rule these tests hold is the surface's own claim: the refusal a reader meets before
 * asking is the refusal the gate answers with. So the signature case files the forbidden
 * verdict for real and asserts the screen carries the gate's sentence, and one case asserts
 * the absence of the transport status — "422" is exactly what must not be shown.
 *
 * The payload shape is pinned too, because it is a contract with the route sibling:
 * `{change_set, author, approval, custodians, files, checked, publishable, refusal}`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
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
  return { ApiError, getCustody: vi.fn(), reviewChangeSet: vi.fn() }
})

vi.mock('@/lib/api', () => api)

import CustodyPage from './CustodyPage'

const AGAINST = `sha256:${'9f'.repeat(32)}`
const MOVED = `sha256:${'9f'.repeat(8)}${'ab'.repeat(24)}`

function record(overrides: Record<string, unknown> = {}) {
  return {
    change_set: {
      id: 'cs-w1-1',
      workspace_id: '/tmp/wt-a',
      summary: 'the workspaces page',
      files: [{ path: 'app/src/pages/WorkspacesPage.tsx', op: 'create', diff_sha: AGAINST }],
      provenance: { session_id: 's-1', agent_id: 'agent-a', why: 'the page the wave asked for' },
      state: 'draft',
    },
    author: 'agent-a',
    approval: null,
    custodians: ['agent-b'],
    files: [
      {
        path: 'app/src/pages/WorkspacesPage.tsx',
        op: 'create',
        recorded: AGAINST,
        current: AGAINST,
        moved: false,
      },
    ],
    checked: true,
    publishable: false,
    refusal: {
      code: 'publish_without_approval',
      sentence: "change set 'cs-w1-1' carries no approval from a reviewer other than its author",
      params: { change_set: 'cs-w1-1' },
    },
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/workspaces/change/cs-w1-1']}>
      <Routes>
        <Route path="/workspaces/change/:id" element={<CustodyPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.getCustody.mockReset()
  api.reviewChangeSet.mockReset()
})

afterEach(cleanup)

describe('a record nobody has signed', () => {
  it('states the stop before it is asked for, and names who can sign it', async () => {
    api.getCustody.mockResolvedValue(record())

    renderPage()

    const page = await screen.findByTestId('custody-page')
    expect(page.getAttribute('data-change-set')).toBe('cs-w1-1')
    expect(screen.getByTestId('custody-author').textContent).toBe('agent-a')
    expect(screen.getByTestId('custody-unsigned').textContent).toContain('agent-a')
    expect(screen.getByTestId('custody-refusal-sentence').textContent).toContain(
      'carries no approval from a reviewer other than its author',
    )
    expect(screen.getByTestId('custody-custodian-list').textContent).toContain('agent-b')
  })

  it('says so plainly when no other agent holds a tree', async () => {
    api.getCustody.mockResolvedValue(record({ custodians: [] }))

    renderPage()

    expect((await screen.findByTestId('custody-custodians')).textContent).toBe(
      'custody.canSignNone',
    )
  })
})

describe('the signature the gate exists to refuse', () => {
  it('carries the sentence the gate refused with, and never the status', async () => {
    api.getCustody.mockResolvedValue(record())
    api.reviewChangeSet.mockRejectedValue(
      new api.ApiError('agent-a authored cs-w1-1 and cannot approve it', 422, ''),
    )

    renderPage()
    const button = await screen.findByTestId('custody-try-sign')
    expect(button.textContent).toContain('custody.tryAs')
    button.click()

    const refusal = await screen.findByTestId('custody-try-refusal')
    expect(refusal.textContent).toContain('agent-a authored cs-w1-1 and cannot approve it')
    expect(refusal.textContent).not.toContain('422')
  })

  it('files the verdict as the author, on a path the set touches', async () => {
    api.getCustody.mockResolvedValue(record())
    api.reviewChangeSet.mockRejectedValue(new api.ApiError('refused', 422, ''))

    renderPage()
    ;(await screen.findByTestId('custody-try-sign')).click()

    expect(api.reviewChangeSet).toHaveBeenCalledWith('cs-w1-1', {
      verdict: 'approve',
      reviewer: 'agent-a',
      reasons: [{ path: 'app/src/pages/WorkspacesPage.tsx', line: 1, why: 'custody.tryReason' }],
    })
  })
})

describe('the bytes the signature covers', () => {
  it('reads both digests and marks where they part', async () => {
    api.getCustody.mockResolvedValue(
      record({
        files: [
          {
            path: 'app/src/pages/WorkspacesPage.tsx',
            op: 'create',
            recorded: AGAINST,
            current: MOVED,
            moved: true,
          },
        ],
        publishable: false,
        refusal: {
          code: 'publish_tree_moved',
          sentence: 'the tree moved after this set was recorded: app/src/pages/WorkspacesPage.tsx',
          params: { paths: 'app/src/pages/WorkspacesPage.tsx' },
        },
      }),
    )

    renderPage()

    const drift = await screen.findByTestId('custody-drift-app/src/pages/WorkspacesPage.tsx')
    // The shared head is printed once and only the part that differs follows it.
    expect(drift.textContent).toContain(`${'9f'.repeat(8)}`)
    expect(drift.textContent).toContain(`${'ab'.repeat(24)}`)
    expect(screen.getByTestId('custody-mark-app/src/pages/WorkspacesPage.tsx').textContent).toBe(
      'custody.moved',
    )
    expect(screen.getByTestId('custody-refusal-sentence').textContent).toContain(
      'the tree moved after this set was recorded',
    )
  })

  it('claims nothing about the disk when the tree is gone', async () => {
    api.getCustody.mockResolvedValue(
      record({
        checked: false,
        files: [
          {
            path: 'app/src/pages/WorkspacesPage.tsx',
            op: 'create',
            recorded: AGAINST,
            current: null,
            moved: false,
          },
        ],
      }),
    )

    renderPage()

    expect((await screen.findByTestId('custody-unchecked')).textContent).toBe('custody.unchecked')
    expect(screen.queryByTestId('custody-drift-app/src/pages/WorkspacesPage.tsx')).toBeNull()
  })

  it('says a signed record can land when nothing moved', async () => {
    api.getCustody.mockResolvedValue(
      record({
        approval: {
          change_set_id: 'cs-w1-1',
          verdict: 'approve',
          reviewer: 'agent-b',
          reasons: [{ path: 'app/src/pages/WorkspacesPage.tsx', line: 1, why: 'reads right' }],
        },
        publishable: true,
        refusal: null,
      }),
    )

    renderPage()

    expect((await screen.findByTestId('custody-signature')).textContent).toContain('agent-b')
    expect(screen.getByTestId('custody-landable').textContent).toContain('agent-b')
    expect(screen.queryByTestId('custody-refusal')).toBeNull()
  })
})
