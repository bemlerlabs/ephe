/**
 * W1 on a phone — the class contract the 390 px measurement in
 * `tests/playwright/mobile-viewport.spec.ts` holds as geometry.
 *
 * jsdom has no layout, so the two rules live here as the tokens a reviewer can read off
 * the DOM, and the browser leg is what turns them into px:
 *
 *   1. below lg (1024 px) every control a thumb aims at reaches the 44 px touch floor
 *      (`max-lg:min-h-11`), the number WD-29 set for the composer;
 *   2. below lg every text entry reaches 16 px (`max-lg:text-ui-input`). iOS Safari zooms
 *      the whole viewport when a focused field computes under 16 px, and the review form
 *      is four fields deep — the zoom pushed its own verdict row off the screen. The
 *      token already exists for this and every other entry in the app sits on it; these
 *      fields carried `text-ui-2xs` (10 px) and `text-ui-xs` (11 px) instead.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
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
  }
})

vi.mock('@/lib/api', () => api)

import WorkspacesPage from './WorkspacesPage'

const WORKSPACES = [
  {
    id: 'w1',
    path: '/work/ephe-wt/w1-ui',
    branch: 'wt/w1-ui',
    state: 'dirty',
    owner: 'w1-ui',
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  },
  {
    id: 'w2',
    path: '/work/ephe-wt/w2-ui',
    branch: 'wt/w2-ui',
    state: 'ready',
    owner: 'w2-ui',
    created_at: new Date(Date.now() - 9 * 60_000).toISOString(),
  },
]

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

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  api.listWorkspaces.mockResolvedValue({ workspaces: WORKSPACES })
  api.listChangeSets.mockResolvedValue({ change_sets: [CHANGE_SET] })
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

const cls = (testid: string) => screen.getByTestId(testid).className

/**
 * The review form's row keys come from a module-level counter, so a row's key is read
 * off the row that rendered instead of assumed — the counter keeps rising across the
 * tests in this file.
 */
async function reasonKeys(): Promise<string[]> {
  const rows = await screen.findAllByTestId(/^review-path-cs-w1-1-/)
  return rows.map((r) => r.getAttribute('data-testid')!.replace('review-path-cs-w1-1-', ''))
}

describe('the workspaces surface on a phone', () => {
  it('the filter is a 44 px entry at the 16 px no-zoom size below lg', async () => {
    renderPage()
    const filter = await screen.findByTestId('workspaces-filter')
    expect(filter.className).toContain('max-lg:min-h-11')
    expect(filter.className).toContain('max-lg:text-ui-input')
    // The field reserves the room its own clear button takes below lg, or the button
    // would sit on top of the text it clears.
    expect(filter.className).toContain('max-lg:pr-11')
  })

  it('the clear button is a 44 px square below lg', async () => {
    renderPage()
    const filter = await screen.findByTestId('workspaces-filter')
    fireEvent.change(filter, { target: { value: 'w1' } })
    expect(cls('workspaces-filter-clear')).toContain('max-lg:w-11')
  })
})

describe('the change-set review on a phone', () => {
  it('every entry in the review form reaches the 44 px floor and the 16 px size', async () => {
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-review-open-cs-w1-1'))
    await screen.findByTestId('review-form-cs-w1-1')
    const [key] = await reasonKeys()

    for (const id of [
      'review-reviewer-cs-w1-1',
      `review-path-cs-w1-1-${key}`,
      `review-line-cs-w1-1-${key}`,
      `review-why-cs-w1-1-${key}`,
    ]) {
      expect(cls(id), `${id} phone floor`).toContain('max-lg:min-h-11')
      expect(cls(id), `${id} no-zoom size`).toContain('max-lg:text-ui-input')
    }
  })

  it('the reason row keeps its file, line and sentence in one group', async () => {
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-review-open-cs-w1-1'))
    const [key] = await reasonKeys()
    const select = screen.getByTestId(`review-path-cs-w1-1-${key}`)
    const row = select.parentElement!
    // One flex row that wraps: path + line on the first line, the sentence below.
    expect(row.className).toContain('flex-wrap')
    expect(row.className).toContain('gap-1.5')
    expect(row.querySelector(`[data-testid="review-why-cs-w1-1-${key}"]`)).not.toBeNull()
  })

  it('the added reason reaches the same floor', async () => {
    renderPage()
    fireEvent.click(await screen.findByTestId('changeset-review-open-cs-w1-1'))
    fireEvent.click(await screen.findByTestId('review-add-cs-w1-1'))
    const keys = await reasonKeys()
    expect(keys).toHaveLength(2)
    const added = keys[1]!
    for (const id of [
      `review-path-cs-w1-1-${added}`,
      `review-line-cs-w1-1-${added}`,
      `review-why-cs-w1-1-${added}`,
    ]) {
      expect(cls(id), `${id} phone floor`).toContain('max-lg:min-h-11')
      expect(cls(id), `${id} no-zoom size`).toContain('max-lg:text-ui-input')
    }
  })
})
