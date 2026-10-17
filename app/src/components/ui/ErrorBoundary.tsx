import { Component, type ReactNode } from 'react'
import type { ErrorInfo } from 'react'
import { useTranslation } from 'react-i18next'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  // A page-scoped fallback that needs the caught error (and the reset) cannot use
  // `fallback` alone, because that node is built before the boundary renders. The
  // render prop is only reached once an error has landed.
  renderFallback?: (error: Error | null, reset: () => void) => ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  // The retry only re-renders the tree that just threw — at the app root that is
  // the whole tree, so it cannot clear the crash on its own. The fallback therefore
  // also offers a reload. Injectable so a test can press it without navigating.
  onReload?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

function defaultReload(): void {
  if (typeof window !== 'undefined') window.location.reload()
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary]', error)
    console.error('[ErrorBoundary] errorInfo:', errorInfo)
    this.props.onError?.(error, errorInfo)
  }

  private reset = () => this.setState({ hasError: false, error: null })

  override render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.renderFallback) {
        return this.props.renderFallback(this.state.error, this.reset)
      }
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <ErrorFallback
          error={this.state.error}
          onReset={this.reset}
          onReload={this.props.onReload ?? defaultReload}
        />
      )
    }
    return this.props.children
  }
}

interface ErrorFallbackProps {
  error: Error | null
  onReset: () => void
  onReload: () => void
}

/**
 * The crash screen the app root falls back to. It does not stop at the failure:
 * the reason is one disclosure away, the next steps are named in the copy, and
 * both of them are controls — retry the render, or reload the app.
 */
function ErrorFallback({ error, onReset, onReload }: ErrorFallbackProps) {
  const { t } = useTranslation()
  return (
    <div
      role="alert"
      data-testid="crash-fallback"
      className="flex flex-col items-center justify-center min-h-[200px] p-6 text-center"
    >
      <div className="w-16 h-16 rounded-full bg-status-danger/10 border border-status-danger/20 flex items-center justify-center mb-4">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-8 w-8 text-status-danger"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>
      <h3 className="text-ui-lg font-semibold text-foreground mb-2">{t('error.crashTitle')}</h3>
      <p className="text-ui-sm text-ink-soft mb-1 max-w-md">{t('error.crashBody')}</p>
      <p data-testid="crash-next" className="text-ui-sm text-ink-soft mb-4 max-w-md">
        {t('error.crashNext')}
      </p>
      {error && (
        <details className="mb-4 w-full max-w-md text-left">
          <summary className="text-ui-xs text-ink-faint cursor-pointer hover:text-ink-soft">
            {t('error.crashDetails')}
          </summary>
          <pre className="text-ui-xs text-status-danger/60 mt-2 bg-canvas rounded-lg p-3 overflow-auto max-h-32">
            {error.message}
          </pre>
        </details>
      )}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onReset}
          data-testid="crash-retry"
          className="bg-brand hover:bg-brand-glow text-black font-medium rounded-xl px-6 py-2 text-ui-sm transition-colors focus-ring"
        >
          {t('error.crashRetry')}
        </button>
        <button
          type="button"
          onClick={onReload}
          data-testid="crash-reload"
          className="rounded-xl border border-hairline px-6 py-2 text-ui-sm font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground focus-ring"
        >
          {t('error.crashReload')}
        </button>
      </div>
    </div>
  )
}

// Re-export for convenience
export { ErrorFallback }
