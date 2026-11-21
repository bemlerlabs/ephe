/**
 * The crash screen the app root falls back to has to name a next step.
 *
 * The defect this pins: the surface stated the failure and stopped at one button,
 * "Try again", which only re-renders the tree that just threw — at the root that is
 * the whole app, so the crash could not clear. Both escapes are here now: retry the
 * render, or reload the app, named in the copy and offered as controls, with the
 * reason one disclosure away and the screen announced to assistive tech.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

function Boom({ when }: { when: boolean }) {
  if (when) throw new Error('the tree fell over')
  return <p data-testid="body">loaded</p>
}

beforeEach(() => {
  // React logs every caught render error; the test asserts on the outcome, not the log.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

describe('ErrorBoundary crash surface', () => {
  it('announces the crash and names the next step in words and controls', () => {
    render(
      <ErrorBoundary>
        <Boom when />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('crash-fallback').getAttribute('role')).toBe('alert')
    expect(screen.getByText('error.crashTitle')).toBeTruthy()
    // The next step is named ...
    expect(screen.getByTestId('crash-next').textContent).toBe('error.crashNext')
    // ... and offered as two controls: retry and reload.
    expect(screen.getByTestId('crash-retry').textContent).toBe('error.crashRetry')
    expect(screen.getByTestId('crash-reload').textContent).toBe('error.crashReload')
  })

  it('carries the reason the tree threw', () => {
    render(
      <ErrorBoundary>
        <Boom when />
      </ErrorBoundary>,
    )
    expect(screen.getByText('the tree fell over')).toBeTruthy()
  })

  it('re-renders on retry once the tree stops throwing', () => {
    const { rerender } = render(
      <ErrorBoundary>
        <Boom when />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('crash-fallback')).toBeTruthy()
    rerender(
      <ErrorBoundary>
        <Boom when={false} />
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByTestId('crash-retry'))
    expect(screen.getByTestId('body').textContent).toBe('loaded')
    expect(screen.queryByTestId('crash-fallback')).toBeNull()
  })

  it('reloads from the reload control', () => {
    const reload = vi.fn()
    render(
      <ErrorBoundary onReload={reload}>
        <Boom when />
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByTestId('crash-reload'))
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('defaults the reload control to a window reload', () => {
    const reload = vi.fn()
    const loc = vi
      .spyOn(window, 'location', 'get')
      .mockReturnValue({ reload } as unknown as Location)
    render(
      <ErrorBoundary>
        <Boom when />
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByTestId('crash-reload'))
    expect(reload).toHaveBeenCalledTimes(1)
    loc.mockRestore()
  })

  it('reports the crash through onError', () => {
    const onError = vi.fn()
    render(
      <ErrorBoundary onError={onError}>
        <Boom when />
      </ErrorBoundary>,
    )
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0]?.[0]).toBeInstanceOf(Error)
  })

  it('hands the decision to a page-scoped renderFallback', () => {
    const seen: Array<Error | null> = []
    render(
      <ErrorBoundary
        renderFallback={(error, reset) => {
          seen.push(error)
          return (
            <button type="button" data-testid="custom" onClick={reset}>
              custom
            </button>
          )
        }}
      >
        <Boom when />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('custom')).toBeTruthy()
    expect(screen.getByTestId('custom').getAttribute('data-testid')).toBe('custom')
    expect(seen[0]?.message).toBe('the tree fell over')
    expect(screen.queryByTestId('crash-fallback')).toBeNull()
  })

  it('renders a plain fallback node when one is given, without the default screen', () => {
    render(
      <ErrorBoundary fallback={<p data-testid="plain">nope</p>}>
        <Boom when />
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('plain')).toBeTruthy()
    expect(screen.queryByTestId('crash-fallback')).toBeNull()
  })
})
