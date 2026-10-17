'use client'

/**
 * I7-2: the audio area in row form — output and recording in one place.
 *
 * The surface used to be called "Sprachausgabe" but also showed the two
 * recording sliders, and under one heading sat five controls without
 * a sentence about them: which of these sends text off the device and which
 * stays local. That is exactly the decision made here, so it stands at the row.
 *
 * Auto-Speak moved over from the privacy section — it is an audio
 * setting, and its switch now writes through `setAutospeak`, which
 * notifies every open tab (the old direct-write path left them silent).
 */
import { Check, Cpu, Gauge, Languages, Mic, Play, Volume2, Wifi } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { LoadingRow } from '@/components/ui'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import Switch from '@/components/shell/Switch'
import { setAutospeak } from '@/lib/autospeak'
import { VOICES } from '../types'
import type { VoiceSettings } from '@/lib/api'
import type { SettingsModel } from './types'

const ENGINES = ['auto', 'piper', 'edge'] as const
const STT_MODELS = ['tiny', 'base', 'small'] as const

function engineHint(cfg: VoiceSettings, t: SettingsModel['t']): string {
  if (cfg.tts_engine === 'piper' && !cfg.piper_available) return t('settings.piperMissing')
  if (cfg.tts_engine === 'edge') return t('settings.engineEdgeHint')
  if (cfg.tts_engine === 'piper') return t('settings.enginePiperHint')
  // Auto is no promise to stay local: without Piper on the machine
  // every output goes to the cloud — the row says so instead of hiding it.
  if (!cfg.piper_available) return t('settings.engineAutoNoPiper')
  return t('settings.engineAutoHint')
}

export function VoiceSection({ model }: { model: SettingsModel }) {
  const {
    autoSpeak,
    handleVoiceSave,
    setAutoSpeak,
    setVoiceCfg,
    t,
    testVoice,
    voiceCfg,
    voiceMsg,
  } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.audioTitle')} subtitle={t('settings.audioSubtitle')} />

      {!voiceCfg ? (
        <LoadingRow label={t('settings.loading')} data-testid="voice-loading" />
      ) : (
        <>
          <SettingsGroup icon={Volume2} title={t('settings.audioGroupOutput')}>
            <SettingsRow
              icon={Cpu}
              title={t('settings.audioEngineRow')}
              description={engineHint(voiceCfg, t)}
              testid="voice-row-engine"
            >
              <div
                role="radiogroup"
                aria-label={t('settings.audioEngineRow')}
                className="flex gap-0.5 rounded-lg bg-surface p-0.5"
              >
                {ENGINES.map((engine) => (
                  <button
                    key={engine}
                    type="button"
                    role="radio"
                    aria-checked={voiceCfg.tts_engine === engine}
                    data-testid={`voice-engine-${engine}`}
                    onClick={() => void handleVoiceSave({ tts_engine: engine })}
                    className={`rounded-md px-3 py-1 text-ui-xs font-medium transition-colors ${
                      voiceCfg.tts_engine === engine
                        ? 'bg-brand/25 text-brand'
                        : 'text-ink-faint hover:text-foreground/80'
                    }`}
                  >
                    {t(`settings.engine_${engine}`)}
                  </button>
                ))}
              </div>
            </SettingsRow>

            <SettingsRow
              icon={Volume2}
              title={t('settings.piperVoice')}
              description={t('settings.piperVoiceHint')}
              testid="voice-row-piper"
            >
              <input
                id="settings-piper-voice"
                value={voiceCfg.piper_voice}
                onChange={(e) => setVoiceCfg({ ...voiceCfg, piper_voice: e.target.value })}
                onBlur={() => void handleVoiceSave({ piper_voice: voiceCfg.piper_voice })}
                placeholder="en_US-amy-medium"
                aria-label={t('settings.piperVoice')}
                spellCheck={false}
                className="w-[200px] max-md:w-[140px] rounded-lg border border-hairline bg-background/60 px-2.5 py-1.5 font-mono text-ui-xs text-foreground/85 placeholder:text-ink-faint focus-ring"
              />
            </SettingsRow>

            <SettingsRow
              icon={Check}
              title={t('settings.audioInstalledVoices')}
              description={
                voiceCfg.installed_piper_voices.length
                  ? t('settings.audioInstalledVoicesHint')
                  : t('settings.piperInstallHint')
              }
              testid="voice-row-installed"
            >
              <span className="flex flex-wrap justify-end gap-1">
                {voiceCfg.installed_piper_voices.map((v) => (
                  <button
                    key={v}
                    type="button"
                    data-testid={`voice-piper-chip-${v}`}
                    onClick={() => void handleVoiceSave({ piper_voice: v })}
                    className={`rounded-md px-1.5 py-0.5 font-mono text-ui-2xs transition-colors ${
                      v === voiceCfg.piper_voice
                        ? 'bg-brand/20 text-brand'
                        : 'bg-surface text-ink-soft hover:text-foreground/80'
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </span>
            </SettingsRow>

            <SettingsRow
              icon={Wifi}
              title={t('settings.edgeVoice')}
              description={t('settings.edgeVoiceHint')}
              testid="voice-row-edge"
            >
              <select
                aria-label={t('settings.edgeVoice')}
                data-testid="voice-edge-select"
                value={voiceCfg.edge_voice}
                onChange={(e) => void handleVoiceSave({ edge_voice: e.target.value })}
                className="min-w-[168px] rounded-lg border border-hairline bg-background/60 px-2.5 py-1.5 text-ui-xs text-foreground/85 focus-ring max-lg:min-h-11"
              >
                {VOICES.map((v) => (
                  <option key={v.id} value={v.id}>
                    {t(v.labelKey)}
                  </option>
                ))}
              </select>
            </SettingsRow>

            <SettingsRow
              icon={Volume2}
              title={t('settings.autoSpeak')}
              description={t('settings.autoSpeakHint')}
              testid="voice-row-autospeak"
            >
              <Switch
                checked={autoSpeak}
                label={t('settings.autoSpeak')}
                testid="autospeak-toggle"
                onChange={(next) => {
                  setAutoSpeak(next)
                  setAutospeak(null, next)
                }}
              />
            </SettingsRow>

            <SettingsRow
              icon={Play}
              title={t('settings.voiceTest')}
              description={t('settings.audioTestHint')}
              testid="voice-row-test"
            >
              <button
                type="button"
                data-testid="voice-test"
                onClick={() => void testVoice()}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-ui-xs font-medium text-foreground/70 transition-colors glass-control hover:text-foreground max-lg:min-h-11"
              >
                <Play className="h-3.5 w-3.5" />
                {t('settings.voiceTest')}
              </button>
            </SettingsRow>
          </SettingsGroup>

          <SettingsGroup icon={Mic} title={t('settings.audioGroupInput')}>
            <SettingsRow
              icon={Gauge}
              title={t('settings.sttModel')}
              description={t('settings.sttModelHint')}
              testid="voice-row-stt-model"
            >
              <select
                aria-label={t('settings.sttModel')}
                data-testid="voice-stt-model"
                value={voiceCfg.stt_model}
                onChange={(e) =>
                  void handleVoiceSave({ stt_model: e.target.value as VoiceSettings['stt_model'] })
                }
                className="min-w-[132px] rounded-lg border border-hairline bg-background/60 px-2.5 py-1.5 text-ui-xs text-foreground/85 focus-ring max-lg:min-h-11"
              >
                {STT_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </SettingsRow>
            <SettingsRow
              icon={Languages}
              title={t('settings.sttLanguage')}
              description={t('settings.sttLanguageHint')}
              testid="voice-row-stt-language"
            >
              <select
                aria-label={t('settings.sttLanguage')}
                data-testid="voice-stt-language"
                value={voiceCfg.stt_language}
                onChange={(e) =>
                  void handleVoiceSave({
                    stt_language: e.target.value as VoiceSettings['stt_language'],
                  })
                }
                className="min-w-[132px] rounded-lg border border-hairline bg-background/60 px-2.5 py-1.5 text-ui-xs text-foreground/85 focus-ring max-lg:min-h-11"
              >
                <option value="auto">{t('settings.sttAuto')}</option>
                <option value="de">Deutsch</option>
                <option value="en">English</option>
              </select>
            </SettingsRow>
          </SettingsGroup>

          {voiceMsg && (
            <p className="font-mono text-ui-xs text-status-danger/80" data-testid="voice-error">
              {voiceMsg}
            </p>
          )}
        </>
      )}
    </div>
  )
}
