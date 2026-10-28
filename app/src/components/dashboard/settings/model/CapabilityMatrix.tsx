import { useEffect, useState } from 'react'
import { ShieldCheck, Sparkles } from 'lucide-react'
import { getCapabilities, type CapabilitiesView } from '@/lib/api'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'

/**
 * G3: the boundary in two rows — the main agent writes and each write passes the
 * gate; a helper is read-only over the guard's own list. The list is fetched, not
 * copied, so this surface cannot promise more than the guard enforces.
 */
export function CapabilityMatrix({
  t,
}: {
  t: (key: string, options?: Record<string, unknown>) => string
}) {
  const [caps, setCaps] = useState<CapabilitiesView | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    getCapabilities()
      .then((view) => {
        if (live) setCaps(view)
      })
      .catch(() => {
        if (live) setFailed(true)
      })
    return () => {
      live = false
    }
  }, [])

  const subDescription = caps
    ? caps.subagent.tools.join(' · ')
    : failed
      ? t('settings.capabilityUnknown')
      : '…'

  return (
    <SettingsGroup
      icon={ShieldCheck}
      title={t('settings.capabilityTitle')}
      description={t('settings.capabilityHint')}
      testid="capability-matrix"
    >
      <SettingsRow
        icon={Sparkles}
        title={t('settings.capabilityMain')}
        description={t('settings.capabilityMainHint')}
        testid="capability-main"
      >
        <span className="text-ui-xs text-ink-faint">{t('settings.capabilityWrites')}</span>
      </SettingsRow>
      <SettingsRow
        icon={ShieldCheck}
        title={t('settings.capabilitySub')}
        description={subDescription}
        testid="capability-sub"
      >
        <span
          data-testid="capability-sub-count"
          className="tabular-nums font-mono text-ui-xs text-ink-faint"
        >
          {caps
            ? `${caps.subagent.tool_count} ${t('settings.capabilityTools')}`
            : failed
              ? '—'
              : '…'}
        </span>
      </SettingsRow>
    </SettingsGroup>
  )
}

/** P1: the two-stage register as one switch instead of a select of raw values. */
export function DetailsModeSwitch({
  value,
  onChange,
  t,
}: {
  value: string
  onChange: (next: 'collapsed' | 'expanded') => void
  t: (key: string, options?: Record<string, unknown>) => string
}) {
  const everyday = value !== 'expanded'
  const options = [
    { key: 'collapsed' as const, label: t('settings.audienceEveryday'), on: everyday },
    { key: 'expanded' as const, label: t('settings.audienceExpert'), on: !everyday },
  ]
  return (
    <SettingsGroup
      icon={Sparkles}
      title={t('settings.audienceTitle')}
      description={t('settings.audienceHint')}
      testid="details-mode-group"
    >
      <div className="flex items-center gap-1 px-3 py-2" role="group">
        {options.map((option) => (
          <button
            key={option.key}
            type="button"
            aria-pressed={option.on}
            data-testid={`details-mode-${option.key}`}
            onClick={() => onChange(option.key)}
            className={`rounded-md border px-2.5 py-1 text-ui-xs transition-colors pointer-coarse:min-h-11 ${
              option.on
                ? 'border-brand/40 bg-brand/10 text-brand'
                : 'border-hairline text-ink-soft hover:text-foreground'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </SettingsGroup>
  )
}
