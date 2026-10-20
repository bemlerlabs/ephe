'use client'

import { useRef, useState } from 'react'
import {
  SettingVerb,
  SettingsGroup,
  SettingsRow,
  VERB_BUTTON,
} from '@/components/shell/SettingsRow'
import {
  appearanceDefaults,
  appearanceProfile,
  parseAppearanceProfile,
  type ProfileReason,
} from './appearanceProfile'
import type { SettingsModel } from './types'

const REASON_KEY: Record<ProfileReason, string> = {
  bad_json: 'settings.appearanceProfileBadJson',
  bad_version: 'settings.appearanceProfileBadVersion',
  unknown_key: 'settings.appearanceProfileUnknownKey',
  invalid_enum: 'settings.appearanceProfileInvalidEnum',
  out_of_range: 'settings.appearanceProfileOutOfRange',
}

function ActionButton({
  testid,
  onClick,
  children,
}: {
  testid: string
  onClick: () => void
  children: string
}) {
  return (
    <button type="button" data-testid={testid} onClick={onClick} className={VERB_BUTTON}>
      {children}
    </button>
  )
}

export function AppearanceProfile({ model }: { model: SettingsModel }) {
  const { deepDraft, deepSections, saveAppearanceProfile, t } = model
  const fields = (deepSections ?? []).find((section) => section.key === 'appearance')?.fields ?? []
  const [status, setStatus] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  function exportProfile() {
    const profile = appearanceProfile(fields, deepDraft.appearance)
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'ephe-appearance.json'
    anchor.click()
    URL.revokeObjectURL(url)
    setStatus({ kind: 'ok', text: t('settings.appearanceProfileExported') })
  }

  async function importFile(file: File) {
    const text = await file.text().catch(() => '')
    const parsed = parseAppearanceProfile(text, fields)
    if (!parsed.ok) {
      setStatus({ kind: 'error', text: t(REASON_KEY[parsed.reason]) })
      return
    }
    const result = await saveAppearanceProfile(parsed.values)
    setStatus(
      result.ok
        ? { kind: 'ok', text: t('settings.appearanceProfileApplied') }
        : {
            kind: 'error',
            text: `${t('settings.appearanceProfileFailed')}${result.detail ? `: ${result.detail}` : ''}`,
          },
    )
  }

  async function resetProfile() {
    const result = await saveAppearanceProfile(appearanceDefaults(fields))
    setStatus(
      result.ok
        ? { kind: 'ok', text: t('settings.appearanceProfileApplied') }
        : { kind: 'error', text: t('settings.appearanceProfileFailed') },
    )
  }

  return (
    <SettingsGroup
      title={t('settings.appearanceProfileTitle')}
      description={t('settings.appearanceProfileHint')}
      testid="appearance-profile-group"
    >
      <SettingsRow
        title={t('settings.appearanceProfileExport')}
        description={t('settings.appearanceProfileExportHint')}
        testid="appearance-profile-export"
      >
        <SettingVerb>
          <ActionButton testid="appearance-profile-export-btn" onClick={exportProfile}>
            {t('settings.appearanceProfileExport')}
          </ActionButton>
        </SettingVerb>
      </SettingsRow>
      <SettingsRow
        title={t('settings.appearanceProfileImport')}
        description={t('settings.appearanceProfileImportHint')}
        testid="appearance-profile-import"
      >
        <SettingVerb>
          <ActionButton
            testid="appearance-profile-import-btn"
            onClick={() => fileInput.current?.click()}
          >
            {t('settings.appearanceProfileImport')}
          </ActionButton>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="sr-only"
            data-testid="appearance-profile-file"
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) void importFile(file)
            }}
          />
        </SettingVerb>
      </SettingsRow>
      <SettingsRow
        title={t('settings.appearanceProfileReset')}
        description={t('settings.appearanceProfileResetHint')}
        testid="appearance-profile-reset"
      >
        <SettingVerb>
          <ActionButton testid="appearance-profile-reset-btn" onClick={() => void resetProfile()}>
            {t('settings.appearanceProfileReset')}
          </ActionButton>
        </SettingVerb>
      </SettingsRow>
      {status && (
        <p
          role={status.kind === 'error' ? 'alert' : 'status'}
          data-testid="appearance-profile-status"
          className={`px-3 py-2 text-scale-data ${
            status.kind === 'error' ? 'text-status-danger' : 'text-ink-faint'
          }`}
        >
          {status.text}
        </p>
      )}
    </SettingsGroup>
  )
}
