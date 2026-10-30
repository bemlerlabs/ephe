/**
 * WS3-19 — accessibility audit of the dashboard surfaces.
 *
 * Roles, names, state attributes and AT-only labels for the inline surfaces
 * (WCAG 2.2.1 keyboard, 2.4.7 focus visible via the global *:focus-visible rule,
 * 4.1.2 name/role/value, 1.3.1 info and relationships, 1.4.1 use of colour).
 * Each assertion pins one attribute that the fix introduced; dropping the
 * attribute again fails the test.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// Fixed i18n table (same style as the sibling component tests).
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'a11y.checkpoints': 'Checkpoints and rollback',
        'checkpoints.create': 'Save snapshot',
        'checkpoints.rollback': 'Rollback to this checkpoint',
        'checkpoints.delete': 'Delete checkpoint',
        'checkpoints.rollbackConfirm': "Rollback to '{{label}}'?",
        'checkpoints.deleteConfirm': "Delete checkpoint '{{label}}'?",
        'chat.askRecommended': 'Recommended',
        'chat.askTakeover': 'Apply',
        'chat.rowWorking': 'Working',
        'chat.rowCompleted': 'Completed',
        'chat.rowFailed': 'Failed',
        'chat.thinkingNow': 'Thinking…',
        'chat.goToMessage': 'Go to message {{n}}',
        'chat.activeMarker': '(active)',
        'metrics.cpu': 'CPU load',
        'metrics.mem': 'Memory',
        'metrics.disk': 'Disk',
      }
      let out = map[key] ?? key
      if (vars) for (const [k, v] of Object.entries(vars)) out = out.replace(`{{${k}}}`, String(v))
      return out
    },
    i18n: { language: 'en' },
  }),
}))

// TypingIndicator reads the store + a media query; framer-motion is stripped to
// plain divs so only the a11y attributes remain in the tree.
vi.mock('@/store/chatStore', () => ({ useChatStore: () => ({ isTyping: true }) }))
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => false }))
vi.mock('framer-motion', async () => {
  const React = await import('react')
  const strip = ({ initial, animate, exit, transition, ...rest }: Record<string, unknown>) => {
    void initial
    void animate
    void exit
    void transition
    return React.createElement('div', rest)
  }
  // The surfaces animate with `m` — LazyMotion's core component; the app root
  // mounts the feature set once (App.tsx). The stub has to answer for `m`.
  return { m: { div: strip } }
})

import AskUserQuestionCard from './AskUserQuestionCard'
import CheckpointControls from './CheckpointControls'
import TimelineRail from './TimelineRail'
import ActivityFeed from './ActivityFeed'
import MetricsGauges from './MetricsGauges'
import TypingIndicator from './TypingIndicator'
import type { ChatCheckpoint } from '@/lib/checkpoints'
import type { ChatMessage } from '@/types'

const askSpec = {
  question: 'Which theme?',
  options: [
    { label: 'Black Forest', description: 'Fir green' },
    { label: 'Nord', description: 'Cool' },
  ],
  recommendation: 'Black Forest',
}

const msgs = (n: number): ChatMessage[] =>
  Array.from({ length: n }, (_, i) => ({
    id: `m${i}`,
    role: 'user' as const,
    content: `msg ${i}`,
    timestamp: Date.now() + i,
  }))

const cp = (label: string): ChatCheckpoint => ({
  id: `cp-${label}`,
  label,
  createdAt: Date.now(),
  messages: [],
})

describe('ws3 a11y — AskUserQuestionCard', () => {
  it('groups the options under the question as an accessible name', () => {
    render(<AskUserQuestionCard spec={askSpec} onPick={vi.fn()} />)
    expect(screen.getByRole('group', { name: 'Which theme?' })).toBeInTheDocument()
  })

  it('exposes the multi-select toggle state via aria-pressed', () => {
    render(<AskUserQuestionCard spec={{ ...askSpec, multiSelect: true }} onPick={vi.fn()} />)
    const first = screen.getByTestId('ask-option-0')
    const second = screen.getByTestId('ask-option-1')
    expect(first).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(first)
    expect(first).toHaveAttribute('aria-pressed', 'true')
    expect(second).toHaveAttribute('aria-pressed', 'false')
  })

  it('hides the decorative ordinal badge from the accessibility tree', () => {
    render(<AskUserQuestionCard spec={askSpec} onPick={vi.fn()} />)
    expect(
      screen.getByTestId('ask-option-0').querySelector('span[aria-hidden="true"]'),
    ).toBeTruthy()
  })
})

describe('ws3 a11y — CheckpointControls', () => {
  const props = {
    checkpoints: [cp('Point 1')],
    onCreate: vi.fn(),
    onRollback: vi.fn(),
    onDelete: vi.fn(),
  }

  it('labels the control group', () => {
    render(<CheckpointControls {...props} checkpoints={[]} />)
    expect(screen.getByRole('group', { name: 'Checkpoints and rollback' })).toBeInTheDocument()
  })

  it('gives every icon-only button a deterministic accessible name', () => {
    render(<CheckpointControls {...props} />)
    expect(screen.getByRole('button', { name: 'Save snapshot' })).toBeInTheDocument()
    // the per-checkpoint actions carry the label so they stay distinguishable
    expect(
      screen.getByRole('button', { name: 'Rollback to this checkpoint: Point 1' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete checkpoint: Point 1' })).toBeInTheDocument()
  })
})

describe('ws3 a11y — TimelineRail', () => {
  it('is a labelled navigation landmark', () => {
    render(<TimelineRail messages={msgs(4)} activeIndex={0} onSelect={vi.fn()} />)
    expect(screen.getByRole('navigation', { name: 'Timeline' })).toBeInTheDocument()
  })

  it('marks only the in-view marker with aria-current', () => {
    render(<TimelineRail messages={msgs(4)} activeIndex={2} onSelect={vi.fn()} />)
    expect(screen.getByTestId('timeline-marker-2')).toHaveAttribute('aria-current', 'true')
    expect(screen.getByTestId('timeline-marker-0')).not.toHaveAttribute('aria-current')
  })
})

describe('ws3 a11y — ActivityFeed', () => {
  it('carries the status as text for screen readers, not colour alone', () => {
    render(
      <ActivityFeed
        activities={[
          { id: 'r', label: 'Fast path', status: 'running' },
          { id: 'd', label: 'Quality check', status: 'done' },
          { id: 'f', label: 'Flaky step', status: 'failed' },
        ]}
      />,
    )
    expect(screen.getByText('Working')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('hides the status glyphs from the accessibility tree', () => {
    const { container } = render(
      <ActivityFeed activities={[{ id: 'r', label: 'Fast path', status: 'running' }]} />,
    )
    expect(
      container.querySelector('[data-testid="activity-r"] svg')?.getAttribute('aria-hidden'),
    ).toBe('true')
  })

})

describe('ws3 a11y — MetricsGauges', () => {
  const metrics = {
    available: true,
    cpu_percent: 12,
    mem_used_mb: 340,
    mem_percent: 20,
    disk_free_bytes: 1,
    disk_free_gb: 1,
    disk_percent: 55,
    uptime_s: 9,
  }

  it('exposes each gauge under its metric name', () => {
    render(<MetricsGauges metrics={metrics} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('CPU load')).toBeInTheDocument()
    expect(screen.getByText('Memory')).toBeInTheDocument()
    expect(screen.getByText('Disk')).toBeInTheDocument()
  })
})

describe('ws3 a11y — TypingIndicator', () => {
  it('announces the thinking state through a status role', () => {
    render(<TypingIndicator />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Thinking…')
    expect(status.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })
})
