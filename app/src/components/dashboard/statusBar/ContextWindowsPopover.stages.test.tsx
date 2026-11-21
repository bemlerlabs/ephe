// Wave 2/B2: the context popover shows the prompt stage by stage, and under the
// workspace rules every file the resolver read with what happened to it.
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import type { ContextBudget } from '@/lib/api'
import { ContextWindowsPopover } from './ContextWindowsPopover'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const BUDGET: ContextBudget = {
  message_count: 2,
  char_count: 40,
  estimated_tokens: 10,
  window_tokens: 8192,
  percent: 0.1,
  compaction_threshold: 28,
  compaction_active: false,
  breakdown: [{ name: 'System prompt', percent: 12 }],
  stages: [
    { name: 'identity', chars: 300, preview: 'id' },
    {
      name: 'workspace_rules',
      chars: 120,
      preview: 'rules',
      files: [
        // Built from parts, like the resolver's own constant: a fixture string must
        // not force the file it names into a snapshot that withholds it.
        { name: 'AGENT' + 'S.md', chars: 40, status: 'included' },
        { name: '.ephe/rules/b.md', chars: 0, status: 'denied', reason: 'outside-root' },
      ],
    },
  ],
}

function renderPopover(budget: ContextBudget | null) {
  render(
    <ContextWindowsPopover
      budget={budget}
      tokens={10}
      window={8192}
      percent={0.1}
      compactionActive={false}
      tokPerSec={null}
      ttftMs={null}
    />,
  )
}

afterEach(cleanup)

describe('ContextWindowsPopover — prompt stages', () => {
  it('lists every stage with its size', () => {
    renderPopover(BUDGET)
    expect(screen.getByTestId('context-stages')).toBeTruthy()
    expect(screen.getByTestId('context-stage-identity').textContent).toContain('300')
    expect(screen.getByTestId('context-stage-workspace_rules').textContent).toContain('120')
  })

  it('names each rule file with the status the resolver reported', () => {
    renderPopover(BUDGET)
    const included = screen.getByTestId('rule-file-included')
    expect(included.textContent).toContain('AGENT' + 'S.md')
    expect(included.textContent).toContain('statusBar.ruleStatus.included')
    const denied = screen.getByTestId('rule-file-denied')
    expect(denied.textContent).toContain('.ephe/rules/b.md')
    expect(denied.textContent).toContain('statusBar.ruleStatus.denied')
    // The stable code rides along, for a reader who wants the why.
    expect(denied.getAttribute('data-status')).toBe('denied')
    expect(denied.getAttribute('data-reason')).toBe('outside-root')
  })

  it('stays quiet when the backend sends no stages', () => {
    renderPopover({ ...BUDGET, stages: undefined })
    expect(screen.queryByTestId('context-stages')).toBeNull()
  })
})
