'use client'

/**
 * A crash inside one data page stays inside that page.
 *
 * The app carries a single boundary at its root. One page that throws during
 * render — a fetch that answered with a shape a child could not read, a lazy
 * chunk that failed to load — therefore took the whole shell down: every route
 * fell to the crash screen until a full reload, so a failure on `/memory` also
 * blanked `/artifacts` and the chat. This boundary sits between the route and the
 * page, so the blast radius is the page. Two escapes are offered: reset the
 * boundary and re-render the page, or leave it for the chat.
 */
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import ErrorBoundary from '@/components/ui/ErrorBoundary'

export default function PageErrorBoundary({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary
      renderFallback={(error, reset) => <PageCrashFallback error={error} onReset={reset} />}
    >
      {children}
    </ErrorBoundary>
  )
}

function PageCrashFallback({ error, onReset }: { error: Error | null; onReset: () => void }) {
  const { t } = useTranslation()
  return (
    <div
      role="alert"
      data-testid="page-error"
      className="flex h-dvh w-full flex-col items-center justify-center gap-4 bg-background p-6 text-center"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-status-danger/20 bg-status-danger/10">
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
      <h1 className="text-ui-lg font-semibold text-foreground">{t('error.pageCrashTitle')}</h1>
      <p className="max-w-md text-ui-sm text-ink-soft">{t('error.pageCrashBody')}</p>
      {error && (
        <details className="w-full max-w-md text-left">
          <summary className="cursor-pointer text-ui-xs text-ink-faint hover:text-ink-soft">
            {t('error.crashDetails')}
          </summary>
          <pre className="mt-2 max-h-32 overflow-auto rounded-lg bg-canvas p-3 text-ui-xs text-status-danger/60">
            {error.message}
          </pre>
        </details>
      )}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onReset}
          data-testid="page-error-retry"
          className="min-h-7 rounded-xl bg-brand px-6 py-2 text-ui-sm font-medium text-black transition-colors hover:bg-brand-glow max-lg:min-h-11 focus-ring"
        >
          {t('error.crashRetry')}
        </button>
        <a
          href="#/chat"
          data-testid="page-error-home"
          className="min-h-7 rounded-xl border border-hairline px-6 py-2 text-ui-sm font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground max-lg:min-h-11 focus-ring"
        >
          {t('error.pageCrashHome')}
        </a>
      </div>
    </div>
  )
}
