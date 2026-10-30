'use client'

import { Box, ShieldCheck } from 'lucide-react'
import Switch from '@/components/shell/Switch'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import type { SettingsModel } from './types'

/** R23 profile register: the four values the server accepts
 *  (core/security_config.py::VALID_APPROVAL_PROFILES, mirrored in
 *  lib/api/types_extra.ts). The surface offers all of them — the code knows four,
 *  so a user must be able to pick four. */
export const APPROVAL_PROFILES = [
  { key: 'strict', labelKey: 'settings.profileStrict' },
  { key: 'session', labelKey: 'settings.profileSession' },
  { key: 'plan', labelKey: 'settings.profilePlan' },
  { key: 'full', labelKey: 'settings.profileFull' },
] as const

export function ApprovalRegister({ model }: { model: SettingsModel }) {
  const { handleSecuritySave, securityCfg, t } = model

  return (
    <SettingsGroup icon={ShieldCheck} title={t('settings.privacyGroupApproval')} testid="behaviour-group-approval">
      <SettingsRow
        icon={ShieldCheck}
        title={t('settings.privacyProfileRow')}
        description={`${t('settings.securityHint')} ${t('settings.profileSessionHint')}`}
        testid="privacy-profile"
      >
        <div
          role="radiogroup"
          aria-label={t('settings.privacyProfileRow')}
          className="flex flex-wrap justify-end gap-1.5"
        >
          {APPROVAL_PROFILES.map((profile) => (
            <button
              key={profile.key}
              type="button"
              role="radio"
              aria-checked={securityCfg?.approval_profile === profile.key}
              onClick={() => void handleSecuritySave({ approval_profile: profile.key })}
              data-testid={`security-profile-${profile.key}`}
              className={`rounded-lg px-3 py-1.5 text-ui-xs font-medium transition-colors ${
                securityCfg?.approval_profile === profile.key
                  ? 'bg-surface-interactive text-ink'
                  : 'text-ink-soft hover:bg-surface-interactive hover:text-ink'
              }`}
            >
              {t(profile.labelKey)}
            </button>
          ))}
        </div>
      </SettingsRow>
      {/* The mode is the other store that gates tools. Named here, where the profile
          is set, so a user who holds both controls knows which one is the ceiling. */}
      <p
        data-testid="privacy-profile-note"
        className="px-3 pb-2 text-ui-xs leading-relaxed text-ink-faint"
      >
        {t('settings.profileModeNote')}
      </p>
      <SettingsRow
        icon={Box}
        title={t('settings.sandboxTitle')}
        description={t('settings.sandboxHint')}
        testid="privacy-sandbox"
      >
        <Switch
          checked={securityCfg?.sandbox_enabled ?? false}
          label={t('settings.sandboxTitle')}
          testid="sandbox-toggle"
          onChange={(next) => void handleSecuritySave({ sandbox_enabled: next })}
        />
      </SettingsRow>
      {/* Wave 2/B3: the one direction an override may go. Asking more is allowed
          per category; nothing here can release a category that asks today. */}
      {(['SAFE', 'NETWORK'] as const).map((category) => {
        const active = securityCfg?.ask_categories?.includes(category) ?? false
        const next = active
          ? (securityCfg?.ask_categories ?? []).filter((entry) => entry !== category)
          : [...(securityCfg?.ask_categories ?? []), category]
        return (
          <SettingsRow
            key={category}
            icon={Box}
            title={t(category === 'SAFE' ? 'settings.askMoreSafe' : 'settings.askMoreNetwork')}
            description={t('settings.askMoreHint')}
            testid={`privacy-ask-${category.toLowerCase()}`}
          >
            <Switch
              checked={active}
              label={t(category === 'SAFE' ? 'settings.askMoreSafe' : 'settings.askMoreNetwork')}
              testid={`ask-${category.toLowerCase()}-toggle`}
              onChange={() => void handleSecuritySave({ ask_categories: next })}
            />
          </SettingsRow>
        )
      })}
    </SettingsGroup>
  )
}
