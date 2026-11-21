import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Coffee } from 'lucide-react'
import { useKeepAwake } from '@/hooks/useKeepAwake'

/**
 * P2-B keep-awake (automations): "keep the computer awake while a chat
 * runs". Persistence (localStorage `ephe_keep_awake`) and the mechanism choice
 * live in useKeepAwake (Tauri IPC → caffeinate, else Web Wake Lock);
 * here only the honest rendering: no mechanism → disabled with a
 * hint (no dead toggle), API fail → hint, active only while a
 * chat is streaming.
 */
export default function KeepAwakeToggle() {
  const { t } = useTranslation()
  const [enabled, setEnabled] = useState(() => localStorage.getItem('ephe_keep_awake') === '1')
  const state = useKeepAwake(enabled)

  const toggle = () => {
    setEnabled((v) => {
      localStorage.setItem('ephe_keep_awake', v ? '0' : '1')
      return !v
    })
  }

  const label = t('automation.keepAwake', {
    defaultValue: 'Keep your computer awake while a chat runs',
  })
  const on = enabled && state.supported

  return (
    <>
      <div
        data-testid="automation-keep-awake"
        className="flex items-center gap-2 rounded-xl bg-surface px-3 py-2"
      >
        <Coffee className="h-3.5 w-3.5 shrink-0 text-ink-soft" />
        <span className="flex-1 min-w-0 text-ui-xs text-foreground/70">
          {label}
          {/* WP2b keep: "aktiv" = the OS wake lock is really being held (live status). */}
          {state.active && (
            <span className="ml-1.5 text-status-success/80">
              · {t('automation.keepAwakeActive', { defaultValue: 'active' })}
            </span>
          )}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label={label}
          disabled={!state.supported}
          onClick={toggle}
          className={`relative w-11 h-6 rounded-full transition-colors duration-base shrink-0 disabled:opacity-40 disabled:cursor-not-allowed ${
            on ? 'bg-brand' : 'bg-surface'
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform duration-base ${
              on ? 'translate-x-5' : ''
            }`}
          />
        </button>
      </div>
      {!state.supported ? (
        <p data-testid="automation-keep-awake-hint" className="text-ui-2xs text-ink-faint">
          {t('automation.keepAwakeUnavailable', {
            defaultValue: 'Not available on this surface — no desktop IPC and no Web Wake Lock.',
          })}
        </p>
      ) : state.error ? (
        <p data-testid="automation-keep-awake-hint" className="text-ui-2xs text-status-danger/80">
          {t('automation.keepAwakeFailed', {
            defaultValue: 'Could not activate keep-awake.',
          })}
        </p>
      ) : null}
    </>
  )
}
