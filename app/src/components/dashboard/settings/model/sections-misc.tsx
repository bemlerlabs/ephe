'use client'

import { Box, Check, Eraser, Languages, Loader2 } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { languageOptions } from './constants'
import { providerLabel } from './constants'
import { dbClearAll } from '@/lib/db'
import { resetTourMarker } from '@/lib/firstRunTour'
import { markSetupIntent } from '@/lib/setupGate'
import { toastBus } from '@/lib/toast'
import { SkyPanel } from '../../SkyCard'
import { SessionStoreSection } from './sections-sessions'
import type { SettingsModel } from './types'

export function renderPersona(model: SettingsModel) {
  const {
    personaLoading,
    personaSaving,
    personaSource,
    personaText,
    savePersona,
    setPersonaText,
    t,
  } = model

  return (
    <div className="space-y-4">
      <div>
        <PageHeader title={t('settings.personaTitle')} subtitle={t('settings.personaSubtitle')} />
        <SettingsGroup
          icon={Box}
          title={t('settings.personaGroup')}
          description={t('settings.personaDesc')}
          testid="persona-group"
        >
          <div className="space-y-2 p-3">
            {personaSource && (
              <p
                data-testid="persona-source"
                className="text-ui-xs font-mono text-ink-faint truncate"
                title={personaSource}
              >
                {t('settings.personaSource')}:{' '}
                {personaSource === 'default' ? t('settings.personaSourceDefault') : personaSource}
              </p>
            )}
            <textarea
              aria-label={t('settings.personaTitle')}
              value={personaText}
              onChange={(e) => setPersonaText(e.target.value.slice(0, 8000))}
              rows={16}
              spellCheck={false}
              placeholder={t('settings.personaPlaceholder')}
              className="w-full glass-control rounded-xl p-3 text-ui-input font-mono text-foreground/90 outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 resize-y leading-relaxed"
            />
            <div className="flex items-center justify-between gap-2">
              <span
                className={`text-ui-xs font-mono ${personaText.length > 8000 ? 'text-status-danger' : 'text-ink-faint'}`}
              >
                {personaText.length} / 8000
              </span>
              <button
                onClick={savePersona}
                disabled={personaSaving || personaLoading || personaText.length > 8000}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand hover:bg-brand-glow disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1.5 text-ui-xs font-medium text-black transition-colors"
              >
                {personaSaving ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                {t('settings.personaSave')}
              </button>
            </div>
            {personaLoading && (
              <p className="text-ui-xs text-ink-faint">{t('settings.personaLoading')}</p>
            )}
          </div>
        </SettingsGroup>
      </div>
    </div>
  )
}

export function renderLanguage(model: SettingsModel) {
  const { selectLanguage, settings, t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.chooseLanguage')} subtitle={t('settings.languageSubtitle')} />
      <SettingsGroup icon={Languages} title={t('settings.languageGroup')} testid="language-group">
        <SettingsRow
          icon={Languages}
          title={t('settings.languageRow')}
          description={t('settings.languageRowHint')}
          testid="language-row"
        >
          <div
            role="radiogroup"
            aria-label={t('settings.languageRow')}
            className="flex gap-0.5 rounded-lg bg-surface p-0.5"
          >
            {languageOptions.map((opt) => (
              <button
                key={opt.code}
                type="button"
                role="radio"
                aria-checked={settings?.language === opt.code}
                data-testid={`language-option-${opt.code}`}
                onClick={() => void selectLanguage(opt.code)}
                className={`rounded-md px-3 py-1 text-ui-xs font-medium transition-colors ${
                  settings?.language === opt.code
                    ? 'bg-surface-interactive text-ink'
                    : 'text-ink-soft hover:bg-surface-interactive hover:text-ink'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </SettingsRow>
      </SettingsGroup>
    </div>
  )
}

export function renderPrivacy(model: SettingsModel) {
  const { confirmClearLocal, setConfirmClearLocal, t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.privacyTitle')} subtitle={t('settings.privacySubtitle')} />

      <SettingsGroup icon={Eraser} title={t('settings.privacyGroupDevice')}>
        <SettingsRow
          icon={Eraser}
          title={t('settings.clearLocalData')}
          description={t('settings.localDataHint')}
          testid="privacy-localdata"
        >
          {confirmClearLocal ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                data-testid="confirm-clear-local"
                onClick={async () => {
                  try {
                    await dbClearAll()
                    setConfirmClearLocal(false)
                    toastBus.success(t('settings.localDataCleared'))
                    setTimeout(() => window.location.reload(), 600)
                  } catch {
                    toastBus.error(t('settings.localDataClearFailed'))
                  }
                }}
                className="rounded-lg border border-status-danger/30 bg-status-danger/20 px-3 py-1.5 text-ui-xs font-medium text-status-danger transition-colors hover:bg-status-danger/30 max-lg:min-h-11"
              >
                {t('settings.confirmClearLocal')}
              </button>
              <button
                type="button"
                onClick={() => setConfirmClearLocal(false)}
                className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/60 transition-colors glass-control hover:text-foreground max-lg:min-h-11"
              >
                {t('settings.cancel')}
              </button>
            </span>
          ) : (
            <button
              type="button"
              data-testid="clear-local-data"
              onClick={() => setConfirmClearLocal(true)}
              className="rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors glass-control hover:bg-status-danger/10 hover:text-foreground max-lg:min-h-11"
            >
              {t('settings.clearLocalData')}
            </button>
          )}
        </SettingsRow>
      </SettingsGroup>

      {/* Wave 4: the other session control on this surface. The Device group above
          clears the browser's copy of a task; this row bounds the files on the
          server's machine — the store `GET /api/sessions` counts. It sits on the
          data surface, not in the design area, because it deletes files. */}
      <SessionStoreSection />

      {/* I6-8: the old bullet list claimed the server listened only on
          127.0.0.1 — starting it with --lan made that line wrong. What the
          server really does now lives where the page asks the server. */}
      <p className="text-ui-xs text-ink-faint" data-testid="privacy-live-note">
        {t('settings.privacyLiveNote')}
      </p>
    </div>
  )
}

export function renderAbout(model: SettingsModel) {
  const { about, t } = model

  return (
    <div className="space-y-3">
      <PageHeader title={t('settings.aboutTitle')} subtitle={t('settings.aboutSubtitle')} />
      {about === null ? (
        <p className="text-ui-xs text-ink-faint">{t('settings.healthFail')}</p>
      ) : (
        <div className="glass-reading rounded-xl p-4 space-y-2 text-ui-xs">
          {[
            [t('settings.aboutVersion'), about.version ?? '—'],
            // The licence the version above is released under. The grant itself lives
            // in the licence file; this row names the identifier a reader has to look
            // up, and the row above names the version it applies to.
            [t('settings.aboutLicense'), 'BUSL-1.1'],
            [t('settings.aboutProvider'), providerLabel(about.active_provider, t)],
            [t('settings.aboutModel'), about.active_model],
            [
              t('settings.aboutOffline'),
              about.offline_capable ? t('settings.yes') : t('settings.no'),
            ],
          ].map(([k, v]) => (
            <div key={k} className="flex items-center justify-between">
              <span className="text-ink-soft">{k}</span>
              <span className="text-foreground/80 font-mono">{v}</span>
            </div>
          ))}
        </div>
      )}
      {/* Onboarding re-entry: the setup route prefills the current engine and
          lets the user choose again — even after onboarding was completed. */}
      <button
        type="button"
        data-testid="about-restart-onboarding"
        onClick={() => {
          // The route only opens on a stated intent (lib/setupGate.ts): without the
          // mark the guard reads the hash as a leftover and leads back to the chat,
          // which made this card a dead end on any machine with an engine chosen.
          markSetupIntent()
          window.location.hash = '#/setup'
        }}
        className="w-full text-left rounded-xl glass-control hover:bg-brand/10 px-3.5 py-2.5 text-ui-xs text-foreground/80 transition-colors"
      >
        {t('settings.aboutRestartOnboarding')}
      </button>
      {/* The first-open tour's replay: the marker is device-level, so the entry
          clears it and reloads into the same first-open state. */}
      <button
        type="button"
        data-testid="about-replay-tour"
        onClick={() => {
          void resetTourMarker().finally(() => window.location.reload())
        }}
        className="mt-2 w-full text-left rounded-xl glass-control hover:bg-brand/10 px-3.5 py-2.5 text-ui-xs text-foreground/80 transition-colors"
      >
        {t('settings.aboutReplayTour')}
      </button>
    </div>
  )
}

export function renderEphemeris(model: SettingsModel) {
  const { t } = model

  return (
    <div className="space-y-3">
      <PageHeader title={t('settings.ephemerisTitle')} subtitle={t('settings.ephemerisSubtitle')} />
      <SkyPanel />
    </div>
  )
}
