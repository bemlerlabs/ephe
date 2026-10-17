/**
 * The boundary that keeps one page's crash inside that page.
 *
 * The defect this pins: with only the app-root boundary, a render error on a data
 * page replaced the whole surface — sibling routes and the shell went with it, and
 * the only recovery was a reload. Here the boundary is a page, a sibling outside it
 * keeps rendering, and the user is offered both a retry and a way back to the chat.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PageErrorBoundary from './PageErrorBoundary'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function Boom({ when }: { when: boolean }) {
  if (when) throw new Error('kepta bridge fell over')
  return <p data-testid="page-body">loaded</p>
}

beforeEach(() => {
  // React logs every caught render error; the test asserts on the outcome, not the log.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

describe('PageErrorBoundary', () => {
  it('shows the page fallback and leaves a sibling outside the boundary untouched', () => {
    render(
      <div>
        <p data-testid="shell">shell still here</p>
        <PageErrorBoundary>
          <Boom when />
        </PageErrorBoundary>
      </div>,
    )
    expect(screen.getByTestId('page-error')).toBeTruthy()
    expect(screen.getByTestId('page-error').getAttribute('role')).toBe('alert')
    // The crash did not reach the app root: a sibling still renders.
    expect(screen.getByTestId('shell').textContent).toBe('shell still here')
    expect(screen.queryByTestId('page-body')).toBeNull()
  })

  it('carries the reason the page threw', () => {
    render(
      <PageErrorBoundary>
        <Boom when />
      </PageErrorBoundary>,
    )
    expect(screen.getByText('kepta bridge fell over')).toBeTruthy()
  })

  it('offers the retry and the way out to the chat', () => {
    render(
      <PageErrorBoundary>
        <Boom when />
      </PageErrorBoundary>,
    )
    // The crash copy names the next step.
    expect(screen.getByText('error.pageCrashBody')).toBeTruthy()
    expect(screen.getByTestId('page-error-retry').textContent).toBe('error.crashRetry')
    expect(screen.getByTestId('page-error-home').getAttribute('href')).toBe('#/chat')
  })

  it('re-renders the page on retry once the page stops throwing', () => {
    const { rerender } = render(
      <PageErrorBoundary>
        <Boom when />
      </PageErrorBoundary>,
    )
    expect(screen.getByTestId('page-error')).toBeTruthy()
    // The page recovers when its inputs change; the boundary holds the fallback
    // until the retry is pressed, then renders the page again.
    rerender(
      <PageErrorBoundary>
        <Boom when={false} />
      </PageErrorBoundary>,
    )
    fireEvent.click(screen.getByTestId('page-error-retry'))
    expect(screen.getByTestId('page-body').textContent).toBe('loaded')
    expect(screen.queryByTestId('page-error')).toBeNull()
  })
})
