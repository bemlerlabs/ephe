/**
 * Issue #193: the shell decided it has no backend for this window, and the surface says so
 * instead of showing a live composer over nothing.
 */
import type { BackendReadiness } from '@/lib/backendReadiness'

export default function BackendNotReady({ readiness }: { readiness: BackendReadiness }) {
  return (
    <div
      data-testid="backend-not-ready"
      role="status"
      className="mx-4 mb-2 rounded-lg border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-ui-xs text-ink-soft"
    >
      <span className="font-medium text-foreground">{readiness.sentence}</span>{' '}
      <span className="text-ink-faint">{readiness.action}</span>
    </div>
  )
}
