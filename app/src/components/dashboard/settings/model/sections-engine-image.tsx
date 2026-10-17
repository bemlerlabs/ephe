'use client'

/**
 * I7-1: the image endpoint in row form — before, three labelled inputs under
 * a heading, without one sentence about what they do.
 *
 * `/image` only works with this endpoint; without it the route answers
 * with an honest refusal. The row therefore states what has to be set
 * for the image tool to do anything at all — and that the key is not written
 * into the register.
 */
import { Loader2, Play, Save, Image as ImageIcon, KeyRound, Server } from 'lucide-react'
import {
  FIELD_COL,
  SettingVerb,
  SettingsGroup,
  SettingsRow,
  VERB_BUTTON,
} from '@/components/shell/SettingsRow'
import type { SettingsModel } from './types'

/** The value column of the register at the data step, flush right. */
const FIELD_CLASS = `${FIELD_COL} max-md:w-32 border border-hairline-strong bg-canvas px-2 py-1 text-right font-mono text-scale-data text-ink placeholder:text-ink-faint focus-ring pointer-coarse:min-h-11 pointer-coarse:text-ui-input`

export function EngineImageGroup({ model }: { model: SettingsModel }) {
  const {
    handleImageSave,
    handleImageTest,
    imageBusy,
    imageCfg,
    imageDraft,
    imageProbe,
    setImageDraft,
    t,
  } = model

  return (
    <SettingsGroup icon={ImageIcon} title={t('settings.imageTitle')} testid="engine-group-image">
      <SettingsRow
        icon={Server}
        title={t('settings.imageBaseUrl')}
        description={t('settings.imageBaseUrlHint')}
        testid="image-row-base-url"
      >
        <input
          id="settings-image-base-url"
          value={imageDraft.base_url}
          onChange={(e) => setImageDraft((d) => ({ ...d, base_url: e.target.value }))}
          placeholder="http://127.0.0.1:8080/v1"
          aria-label={t('settings.imageBaseUrl')}
          spellCheck={false}
          className={FIELD_CLASS}
        />
        <SettingVerb />
      </SettingsRow>
      <SettingsRow
        icon={ImageIcon}
        title={t('settings.imageModel')}
        description={t('settings.imageModelHint')}
        testid="image-row-model"
      >
        <input
          id="settings-image-model"
          value={imageDraft.model}
          onChange={(e) => setImageDraft((d) => ({ ...d, model: e.target.value }))}
          placeholder="sd-1.5"
          aria-label={t('settings.imageModel')}
          spellCheck={false}
          className={FIELD_CLASS}
        />
        <SettingVerb />
      </SettingsRow>
      <SettingsRow
        icon={KeyRound}
        title={t('settings.imageApiKey')}
        description={
          imageCfg?.has_api_key
            ? t('settings.imageKeySet', { hint: imageCfg.api_key_hint })
            : t('settings.imageApiKeyHint')
        }
        testid="image-row-apikey"
      >
        <input
          id="settings-image-api-key"
          type="password"
          value={imageDraft.api_key}
          onChange={(e) => setImageDraft((d) => ({ ...d, api_key: e.target.value }))}
          placeholder="optional"
          aria-label={t('settings.imageApiKey')}
          className={FIELD_CLASS}
        />
        <SettingVerb />
      </SettingsRow>
      <SettingsRow
        icon={Play}
        title={t('settings.imageTest')}
        description={imageProbe ? t('settings.imageProbeHint') : t('settings.imageIdleHint')}
        testid="image-row-actions"
      >
        <button
          type="button"
          disabled={imageBusy}
          data-testid="settings-image-save"
          onClick={() => void handleImageSave()}
          className={VERB_BUTTON}
        >
          <Save className="h-3 w-3" />
          {t('settings.imageSave')}
        </button>
        <button
          type="button"
          disabled={imageBusy}
          data-testid="settings-image-test"
          onClick={() => void handleImageTest()}
          className={VERB_BUTTON}
        >
          {imageBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
          {t('settings.imageTest')}
        </button>
      </SettingsRow>
      {imageProbe && (
        <p className="pl-6 text-scale-data text-ink-soft" data-testid="image-probe">
          {imageProbe.reachable
            ? t('settings.imageProbeOk', {
                count: imageProbe.models.length,
                model: imageProbe.models[0] || '—',
              })
            : t('settings.imageProbeFail', { detail: imageProbe.detail })}
        </p>
      )}
    </SettingsGroup>
  )
}
