'use client'

/**
 * I7-1: the engine area in row form — before it was a stack of cards.
 *
 * The engine is the product's most important surface (here the agent is run)
 * and the only one that still spoke in the old handwriting: a grey card, then
 * a model-list stack, then inputs without one sentence about what they change.
 * Now the same pattern as everywhere: a group with subhead and icon, every
 * control its own row with its own explanation, the value on the right.
 *
 * The principle stays: there is no silent default. Without a chosen engine
 * `engineNotConfigured` remains, and the endpoint is what the user stored —
 * the surface does not guess.
 */
import { useMemo, useState } from 'react'
import { KeyRound, Cpu, FileOutput, FolderInput, Zap } from 'lucide-react'
import { ModelPicker } from '@/components/model/ModelPicker'
import { rowsFromOptions } from '@/components/model/modelPickerTypes'
import PageHeader from '@/components/shell/PageHeader'
import {
  FIELD_COL,
  SettingValue,
  SettingVerb,
  SettingsGroup,
  SettingsRow,
  VERB_BUTTON,
} from '@/components/shell/SettingsRow'
import { CONTROL_CLASS } from '@/components/shell/SettingControl'
import EnvironmentTools from '@/components/shell/EnvironmentTools'
import { engineStateOf, providerLabel } from './constants'
import { DeepFields } from './deepFields'
import { EngineImageGroup } from './sections-engine-image'
import type { SettingsModel } from './types'

/** A path or an address the row edits: the register's native field, right-aligned
 *  so values of adjacent rows meet on one edge. */
const FIELD = `${FIELD_COL} max-md:w-32 ${CONTROL_CLASS} text-right placeholder:text-ink-faint pointer-coarse:min-h-11 pointer-coarse:text-ui-input`

export function EngineSection({ model }: { model: SettingsModel }) {
  const {
    checkHealth,
    customApiKey,
    customOption,
    isOllamaFamily,
    customEndpoint,
    displayModels,
    engineHealth,
    engineTesting,
    liveModels,
    outputDraft,
    setCustomApiKey,
    setCustomEndpoint,
    setOutputDraft,
    setSettings,
    settings,
    t,
  } = model

  const active = settings?.provider
  // S2: the picker's choice is pending until "Use" writes it, so the row that carries
  // `engine-row-model-*` always names a model the user actually picked — never one the
  // list happened to start with.
  const [pending, setPending] = useState('')
  const modelRows = useMemo(
    () => rowsFromOptions(liveModels, active ? providerLabel(active.type, t) : ''),
    [liveModels, active, t],
  )
  const activeModel = settings?.provider.model ?? ''
  const shownModel = pending || activeModel
  // The row states a condition, so it reads what the backend says about itself: the
  // three engine states, plus the fourth fact they cannot carry — an engine that
  // answered and refused this start's credential.
  const engineState = engineHealth ? engineStateOf(engineHealth) : null
  const keyRefused = Boolean(engineHealth?.engine_key_challenge)
  const keyHeld = Boolean(engineHealth?.engine_key_configured)

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.engineTitle')} subtitle={t('settings.engineSubtitle')} />

      <SettingsGroup icon={Zap} title={t('settings.activeEngine')} testid="settings-active-engine">
        <SettingsRow
          icon={Cpu}
          title={active ? providerLabel(active.type, t) : t('settings.engineNotConfigured')}
          description={
            active
              ? t('settings.activeEndpoint', { url: active.endpoint || '—' })
              : t('settings.activeProviderMissing')
          }
          testid="engine-row-active"
        >
          {engineState && (
            <SettingValue
              data-testid="settings-engine-state"
              data-engine-state={engineState}
              data-engine-key={keyRefused ? 'refused' : undefined}
              now={engineTesting}
            >
              {keyRefused
                ? t('settings.engineKeyChallenge')
                : t(`settings.engineState.${engineState}`)}
            </SettingValue>
          )}
          <SettingVerb>
            <button
              type="button"
              data-testid="settings-engine-test"
              onClick={() => void checkHealth()}
              disabled={engineTesting}
              className={VERB_BUTTON}
            >
              {engineTesting ? '…' : t('settings.engineTest')}
            </button>
          </SettingVerb>
        </SettingsRow>
      </SettingsGroup>

      <SettingsGroup
        icon={Cpu}
        title={t('settings.chooseModel')}
        description={t('settings.modelListHint')}
        testid="engine-group-model"
      >
        <div className="px-3 pb-1.5">
          <ModelPicker
            id="engine-model-picker"
            testId="engine-model-picker"
            label={t('settings.chooseModel')}
            placeholder={t('modelPicker.choose')}
            rows={modelRows}
            value={pending || activeModel}
            onChange={setPending}
          />
        </div>
        {shownModel &&
          (() => {
            const chip = displayModels.find((opt) => opt.id === shownModel)
            const stated = liveModels.find((opt) => opt.name === shownModel)
            return (
              <SettingsRow
                icon={Cpu}
                title={chip?.label ?? shownModel}
                description={
                  stated?.supports_tools === false
                    ? t('modelPicker.answerOnly')
                    : chip && 'descKey' in chip && chip.descKey
                      ? t(chip.descKey)
                      : chip?.desc
                }
                testid={`engine-row-model-${shownModel}`}
              >
                {/* The stored model is a state, so it wears the data column and no
                    accent: the accent marks what is running at this moment. */}
                <SettingValue>
                  {shownModel === activeModel ? t('settings.modelInUse') : ''}
                </SettingValue>
                <SettingVerb>
                  <button
                    type="button"
                    onClick={() => {
                      setSettings((prev) =>
                        prev
                          ? { ...prev, provider: { ...prev.provider, model: shownModel } }
                          : prev!,
                      )
                      setPending('')
                    }}
                    data-testid={`engine-model-${shownModel}`}
                    className={VERB_BUTTON}
                  >
                    {t('settings.modelUse')}
                  </button>
                </SettingVerb>
              </SettingsRow>
            )
          })()}
        {isOllamaFamily && (
          <SettingsRow
            icon={Cpu}
            title={customOption.label}
            description={t(customOption.descKey)}
            testid="engine-row-model-custom"
          >
            <SettingValue>
              {settings?.provider.type === 'custom_ollama' ? t('settings.modelInUse') : ''}
            </SettingValue>
            <SettingVerb>
              <button
                type="button"
                role="radio"
                aria-checked={settings?.provider.type === 'custom_ollama'}
                onClick={() =>
                  setSettings((prev) =>
                    prev
                      ? { ...prev, provider: { ...prev.provider, type: 'custom_ollama' } }
                      : {
                          provider: { type: 'custom_ollama', model: '' },
                          memory_enabled: true,
                          language: 'de',
                        },
                  )
                }
                data-testid="engine-model-custom"
                className={VERB_BUTTON}
              >
                {t('settings.modelUse')}
              </button>
            </SettingVerb>
          </SettingsRow>
        )}
      </SettingsGroup>

      {customEndpoint && (
        <SettingsGroup
          icon={KeyRound}
          title={t('settings.engineAccess')}
          testid="engine-group-access"
        >
          <SettingsRow
            icon={Zap}
            title={t('settings.endpointLabel')}
            description={t('settings.endpointHint')}
            testid="engine-row-endpoint"
          >
            <input
              id="settings-endpoint"
              value={customEndpoint}
              onChange={(e) => setCustomEndpoint(e.target.value)}
              placeholder="http://localhost:11434"
              aria-label={t('settings.endpointLabel')}
              spellCheck={false}
              className={FIELD}
            />
            <SettingVerb />
          </SettingsRow>
          <SettingsRow
            icon={KeyRound}
            title={t('settings.apiKeyLabel')}
            description={
              keyRefused
                ? t(keyHeld ? 'settings.engineKeyRejected' : 'settings.engineKeyMissing')
                : t('settings.apiKeyHint')
            }
            testid="engine-row-apikey"
          >
            <input
              id="settings-api-key"
              type="password"
              value={customApiKey}
              onChange={(e) => setCustomApiKey(e.target.value)}
              placeholder="sk-..."
              aria-label={t('settings.apiKeyLabel')}
              className={FIELD}
            />
            <SettingVerb />
          </SettingsRow>
        </SettingsGroup>
      )}

      <SettingsGroup
        icon={FolderInput}
        title={t('settings.engineFolders')}
        testid="engine-group-folders"
      >
        <SettingsRow
          icon={FileOutput}
          title={t('settings.outputDirTitle')}
          description={t('settings.outputDirRowHint')}
          testid="engine-row-output"
        >
          <input
            data-testid="settings-output-dir"
            value={outputDraft}
            onChange={(e) => setOutputDraft(e.target.value)}
            placeholder="~/Downloads"
            aria-label={t('settings.outputDirTitle')}
            spellCheck={false}
            className={FIELD}
          />
          <SettingVerb />
        </SettingsRow>
      </SettingsGroup>

      <EngineImageGroup model={model} />

      <SettingsGroup icon={Cpu} title={t('environment.title')} testid="settings-environment">
        <SettingsRow
          icon={Zap}
          title={t('environment.title')}
          description={t('environment.settingsHint')}
          testid="engine-row-environment"
        />
        <div className="pb-3 pl-6">
          <EnvironmentTools
            onPick={(pick) => {
              setSettings((prev) =>
                prev
                  ? {
                      ...prev,
                      provider: {
                        ...prev.provider,
                        type: pick.providerKind,
                        model: pick.model,
                        endpoint: pick.endpoint ?? prev.provider.endpoint,
                      },
                    }
                  : prev,
              )
              if (pick.endpoint) setCustomEndpoint(pick.endpoint)
            }}
          />
        </div>
      </SettingsGroup>

      {/* I3-V5: the engine gate lives here, not in an expert box. */}
      <DeepFields model={model} prefixes={['advanced.']} />
    </div>
  )
}
