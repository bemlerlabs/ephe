/**
 * Wave 3 (web intake): the source cards a `web_research` call opens.
 *
 * jsdom has no layout, so the 320 px floor lives here as the class contract a
 * reviewer can read off the DOM: the panel shrinks (`min-w-0 max-w-full`) and
 * every text node that can be a URL or a long title wraps (`break-words`,
 * `break-all`) instead of forcing the column wide. The browser leg that turns
 * the classes into pixels is the mobile viewport spec.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'

const api = vi.hoisted(() => ({ getResearchEvidence: vi.fn() }))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getResearchEvidence: api.getResearchEvidence,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
  }),
}))

import { ResearchEvidence } from './ResearchEvidence'
import type { ToolCall } from '@/types'

const TOOL: ToolCall = {
  id: 'call-1',
  name: 'web_research',
  args: { query: 'moon drift' },
  result: '[web_research] query="moon drift"',
  status: 'completed',
}

const ANSWER = {
  ok: true,
  total: 2,
  runs: [
    {
      run_id: 'r_1',
      query: 'moon drift',
      site: '',
      started_at: '2026-11-12T00:00:00Z',
      provider: 'configured',
      depth: 1,
      freshness: '',
      pages: 1,
      considered: 1,
      sources: 1,
      workspace: 1,
      claims: [],
      answer: [],
      gaps: [],
      verification: { checked: 2, verified: 2, issues: [] },
      turn_id: 'turn-1',
    },
  ],
  sources: [
    {
      source_id: 's_a66928a39d45',
      url: 'https://example.org/moon',
      title: 'Moon drift',
      fetched_at: '2026-11-12T00:00:00Z',
      sha256: 'a'.repeat(64),
      excerpt: 'The moon drifts away from Earth at about 3.8 cm per year.',
      query: 'moon drift',
      run_id: 'r_1',
    },
  ],
  workspace: [
    {
      path: 'src/drift.py',
      line: 4,
      reference: 'src/drift.py:4',
      text: 'RATE_CM_PER_YEAR = 3.8',
      query: 'moon drift',
      run_id: 'r_1',
    },
  ],
}

beforeEach(() => {
  api.getResearchEvidence.mockReset()
})

afterEach(cleanup)

describe('ResearchEvidence', () => {
  it('renders a card per page and one row per workspace line', async () => {
    api.getResearchEvidence.mockResolvedValue(ANSWER)
    render(<ResearchEvidence tool={TOOL} />)

    const panel = await screen.findByTestId('research-evidence')
    expect(screen.getByText('Moon drift')).toBeInTheDocument()
    expect(screen.getByText('[s_a66928a39d45]')).toBeInTheDocument()
    expect(screen.getByText('src/drift.py:4')).toBeInTheDocument()
    expect(screen.getByText('RATE_CM_PER_YEAR = 3.8')).toBeInTheDocument()
    expect(screen.getByTestId('research-verification').textContent).toContain(
      'chat.research.citationAll',
    )
    expect(panel.getAttribute('data-testid')).toBe('research-evidence')
  })

  it('asks the route for the query the tool carried', async () => {
    api.getResearchEvidence.mockResolvedValue(ANSWER)
    render(<ResearchEvidence tool={TOOL} />)
    await screen.findByTestId('research-evidence')
    expect(api.getResearchEvidence).toHaveBeenCalledWith(
      { query: 'moon drift', limit: 8 },
      expect.any(AbortSignal),
    )
  })

  it('renders nothing when the route has no evidence to show', async () => {
    api.getResearchEvidence.mockResolvedValue({
      ok: true,
      runs: [],
      sources: [],
      workspace: [],
      total: 0,
    })
    render(<ResearchEvidence tool={TOOL} />)
    await waitFor(() => expect(api.getResearchEvidence).toHaveBeenCalled())
    expect(screen.queryByTestId('research-evidence')).not.toBeInTheDocument()
  })

  it('keeps the tool result as the fallback when the list fails', async () => {
    api.getResearchEvidence.mockRejectedValue(new Error('offline'))
    render(<ResearchEvidence tool={TOOL} />)
    await waitFor(() => expect(api.getResearchEvidence).toHaveBeenCalled())
    expect(screen.queryByTestId('research-evidence')).not.toBeInTheDocument()
  })

  it('does not ask before the call finished', () => {
    render(<ResearchEvidence tool={{ ...TOOL, status: 'pending' }} />)
    expect(api.getResearchEvidence).not.toHaveBeenCalled()
  })

  it('wraps at the 320 px floor instead of forcing the column wide', async () => {
    api.getResearchEvidence.mockResolvedValue(ANSWER)
    render(<ResearchEvidence tool={TOOL} />)

    const panel = await screen.findByTestId('research-evidence')
    expect(panel.className).toContain('min-w-0')
    expect(panel.className).toContain('max-w-full')
    expect(panel.className).not.toMatch(/\bw-\[\d+px\]/)

    const card = screen.getByTestId('research-source-card')
    expect(card.className).toContain('w-full')
    expect(card.className).toContain('min-w-0')
    expect(screen.getByText('Moon drift').className).toContain('break-words')
    expect(panel.querySelector('.break-all')).not.toBeNull()
  })
})
