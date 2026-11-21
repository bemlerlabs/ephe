// The report's three honest states: the prompt it read, an empty prompt the
// backend reported, and a backend that did not answer. The badge text is the
// resolver's status word; a status the report has no label for renders as itself.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { loadContextReport, parseContextReport } from '@/lib/api/contextReport'
import ContextReport from './ContextReport'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${JSON.stringify(opts)}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/lib/api/contextReport', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/contextReport')>()
  return { ...actual, loadContextReport: vi.fn() }
})

const loader = vi.mocked(loadContextReport)

const PAYLOAD = {
  total_chars: 16_000,
  stages: [
    { name: 'identity', chars: 700, preview: 'You are Ephe' },
    {
      name: 'workspace_rules',
      chars: 15_300,
      preview: '## Project rules',
      files: [
        { name: 'AGEN' + 'TS.md', chars: 400, status: 'included' },
        { name: '.ephe/rules/big.md', chars: 6_000, status: 'truncated' },
        {
          name: '.ephe/rules/locked.md',
          chars: 0,
          status: 'denied',
          reason: 'protected-root',
        },
        { name: '.ephe/rules/late.md', chars: 0, status: 'skipped', reason: 'no-budget' },
        { name: '.ephe/rules/odd.md', chars: 3, status: 'quarantined' },
      ],
    },
  ],
}

function respond(payload: unknown) {
  loader.mockResolvedValue(parseContextReport(payload))
}

async function renderLoaded() {
  render(<ContextReport />)
  return screen.findByTestId('context-report-total')
}

beforeEach(() => {
  loader.mockReset()
})

afterEach(cleanup)

describe('ContextReport', () => {
  it('shows the total and each layer with its share', async () => {
    respond(PAYLOAD)
    const total = await renderLoaded()
    expect(total.textContent).toContain('16,000')
    expect(total.textContent).toContain('settings.context.layersCount')

    const identity = screen.getByTestId('context-report-stage-identity')
    expect(identity.textContent).toContain('settings.context.stage.identity')
    expect(identity.textContent).toContain('700')
    expect(identity.textContent).toContain('settings.context.stageFigures')
    // 700 of 16,000 = 4.4% of the prompt
    expect(identity.textContent).toContain('4.4')
  })

  it('names every rule file with the status the resolver reported', async () => {
    respond(PAYLOAD)
    await renderLoaded()
    expect(screen.getAllByTestId('context-report-file')).toHaveLength(5)

    const included = screen.getByTestId('context-report-badge-included')
    expect(included.textContent).toContain('statusBar.ruleStatus.included')

    const denied = screen.getByTestId('context-report-badge-denied')
    expect(denied.textContent).toContain('statusBar.ruleStatus.denied')
    expect(denied.getAttribute('data-status')).toBe('denied')

    const locked = screen
      .getAllByTestId('context-report-file')
      .find((row) => row.textContent?.includes('locked.md'))
    expect(locked?.getAttribute('data-reason')).toBe('protected-root')
    expect(locked?.textContent).toContain('settings.context.fileReason')
    expect(locked?.textContent).toContain('protected-root')

    // A status this build has no label for is not translated into a status it knows.
    const odd = screen.getByTestId('context-report-badge-quarantined')
    expect(odd.textContent).toBe('quarantined')
  })

  it('shows the caps that were hit and what still arrived', async () => {
    respond(PAYLOAD)
    await renderLoaded()
    const caps = screen.getByTestId('context-report-caps-body')
    expect(caps.textContent).toContain('settings.context.capsTruncated')
    expect(caps.textContent).toContain('6,000')
    expect(caps.textContent).toContain('settings.context.capsSkipped')
  })

  it('says no cap was hit when every file fit', async () => {
    respond({
      total_chars: 400,
      stages: [
        {
          name: 'workspace_rules',
          chars: 400,
          files: [{ name: 'x.md', chars: 400, status: 'included' }],
        },
      ],
    })
    await renderLoaded()
    expect(screen.getByTestId('context-report-caps-body').textContent).toContain(
      'settings.context.capsNone',
    )
  })

  it('says no rule file was reported instead of pretending nothing was capped', async () => {
    respond({ total_chars: 700, stages: [{ name: 'identity', chars: 700 }] })
    await renderLoaded()
    expect(screen.getByTestId('context-report-caps-body').textContent).toContain(
      'settings.context.capsNoFiles',
    )
    expect(screen.queryByTestId('context-report-file')).toBeNull()
  })

  it('has an honest empty state when the backend reports no stage', async () => {
    respond({ stages: [], total_chars: 0 })
    render(<ContextReport />)
    const empty = await screen.findByTestId('context-report-empty')
    expect(empty.textContent).toContain('settings.context.emptyTitle')
    expect(empty.textContent).toContain('settings.context.emptyBody')
    expect(screen.queryByTestId('context-report-stages')).toBeNull()
    expect(screen.queryByTestId('context-report-total')).toBeNull()
  })

  it('stays an error when the backend does not answer, and retries on request', async () => {
    loader.mockRejectedValueOnce(new Error('offline'))
    render(<ContextReport />)
    const error = await screen.findByRole('alert')
    expect(error.textContent).toContain('settings.context.unreachable')

    respond(PAYLOAD)
    fireEvent.click(screen.getByTestId('context-report-retry'))
    await waitFor(() => expect(screen.getByTestId('context-report-total')).toBeTruthy())
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('keeps the file rows wrappable for the 320 px floor', async () => {
    respond(PAYLOAD)
    await renderLoaded()
    const row = screen.getAllByTestId('context-report-file')[0]!
    expect(row.className).toContain('flex-wrap')
    const name = row.querySelector('span')
    expect(name?.className).toContain('min-w-0')
    expect(name?.className).toContain('truncate')
  })
})
