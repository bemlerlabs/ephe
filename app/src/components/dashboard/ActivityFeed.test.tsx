/**
 * Ephe — PWA-Chat-UX-Plan, Task B3: ActivityFeed
 *
 * GIVEN  ActivityFeed with activities (running/done/failed)
 * WHEN   rendered
 * THEN   aria-live="polite", status icons (running = spin), labels
 */
import { describe, it, expect, afterEach, afterAll } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import i18n from '@/i18n'
import ActivityFeed from './ActivityFeed'
import type { Activity } from '@/types'

const act = (p: Partial<Activity> & { id: string }): Activity => ({
  label: 'Label',
  status: 'done',
  ...p,
})

/** Eleven plain labels: three fold into the counter, eight stay (FEED_CAP). */
const overflowFeed = (): Activity[] => Array.from({ length: 11 }, (_, i) => act({ id: `a${i}` }))

afterEach(cleanup)

describe('ActivityFeed', () => {
  it('rendert null bei leerem/fehlendem Array', () => {
    const empty = render(<ActivityFeed activities={[]} />)
    expect(empty.container.firstChild).toBeNull()
    const undef = render(<ActivityFeed />)
    expect(undef.container.firstChild).toBeNull()
  })

  it('rendert alle Labels', () => {
    render(
      <ActivityFeed
        activities={[
          act({ id: '1', label: 'Fast path', status: 'done' }),
          act({ id: '2', label: 'Quality check', status: 'running' }),
        ]}
      />,
    )
    expect(screen.getByText('Fast path')).toBeInTheDocument()
    expect(screen.getByText('Quality check')).toBeInTheDocument()
  })

  it('hat aria-live="polite" am Container', () => {
    const { container } = render(
      <ActivityFeed activities={[act({ id: '1', label: 'X', status: 'running' })]} />,
    )
    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull()
  })

  it('running-Entry hat animiertes Icon (animate-spin)', () => {
    const { container } = render(
      <ActivityFeed activities={[act({ id: '1', label: 'X', status: 'running' })]} />,
    )
    expect(container.querySelector('.animate-spin')).not.toBeNull()
  })

  it('caps the feed at more than FEED_CAP entries', () => {
    render(<ActivityFeed activities={overflowFeed()} />)
    expect(screen.getByTestId('activity-overflow')).toBeInTheDocument()
    // the last FEED_CAP lines stay, the three before them fold into the counter
    expect(screen.queryByTestId('activity-a2')).toBeNull()
    expect(screen.getByTestId('activity-a3')).toBeInTheDocument()
    expect(screen.getByTestId('activity-a10')).toBeInTheDocument()
  })
})

/**
 * Locale leak (finding 2026-10-08): the overflow counter was a hardcoded German text
 * node — the German form of `… {overflow} more` — so it stayed German inside an English UI. The label
 * now comes from `chat.activityMore`, and this is the bar that the text node slipped:
 * the rendered line has to follow the active language in both shipped locales. Put the
 * German back into the component and the English assertion fails.
 */
describe('ActivityFeed — the overflow line follows the active language', () => {
  it('renders the German overflow label from the locale', async () => {
    await i18n.changeLanguage('de')
    render(<ActivityFeed activities={overflowFeed()} />)
    expect(screen.getByTestId('activity-overflow').textContent?.trim()).toBe('… 3 weitere')
  })

  it('renders the English label and no German word', async () => {
    await i18n.changeLanguage('en')
    render(<ActivityFeed activities={overflowFeed()} />)
    expect(screen.getByTestId('activity-overflow').textContent?.trim()).toBe('… 3 more')
    expect(screen.queryByText(/weitere/)).toBeNull()
  })

  afterAll(async () => {
    await i18n.changeLanguage('en')
  })
})
