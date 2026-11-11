import { useTranslation } from 'react-i18next'

/**
 * B1/B2: the engine's state as one quiet line in the top bar, where the run
 * already reads. The box that used to float over the empty canvas said the same
 * thing on top of the work; this says it once, at the edge, and its click is the
 * way to the engine settings that can change it.
 *
 * `unknown` is the state where the answer cannot be read at all — the backend that probes
 * the engine is itself unreachable. Saying "checking" there would promise a probe that is
 * not running, and the status strip below already says the true reason on the same screen.
 */
export type EnginePillState = 'online' | 'offline' | 'checking' | 'unknown'

export default function EngineStatusPill({
  state,
  onClick,
}: {
  state: EnginePillState
  onClick: () => void
}) {
  const { t } = useTranslation()
  const label =
    state === 'online'
      ? t('welcome.modelOnline')
      : state === 'checking'
        ? t('welcome.modelChecking', { defaultValue: 'Checking the engine' })
        : state === 'unknown'
          ? t('welcome.modelStatusUnknown')
          : t('welcome.modelOffline')
  const dot =
    state === 'online'
      ? 'bg-status-success'
      : state === 'checking' || state === 'unknown'
        ? 'bg-mist/40'
        : 'bg-status-warning'
  return (
    <>
      <button
        type="button"
        data-testid="engine-status-pill"
        data-engine-state={state}
        aria-label={label}
        title={label}
        onClick={onClick}
        className="hidden lg:inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dot}`} aria-hidden="true" />
        <span className="whitespace-nowrap">{label}</span>
      </button>
      {/* role=status is not allowed on a button; the changing state is announced
          from its own live node, the control stays a control. */}
      <span role="status" aria-live="polite" data-testid="engine-status-live" className="sr-only">
        {label}
      </span>
    </>
  )
}
