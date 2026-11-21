'use client'

// I3-3/I3-9: the generation levers in the row pattern.
//
// Range, description and step come from the payload
// (core/engine_config.py::GENERATION_BOUNDS + core/settings_hints.py::
// GENERATION_HINTS). Before, '0–2' and '1–40' stood as text in the TSX, and the
// six number fields were grey bars without a border in the light theme.
import PageHeader from '@/components/shell/PageHeader'
import SettingControl from '@/components/shell/SettingControl'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { generationIcon } from '@/components/shell/settingsIcons'
import type { SettingsModel } from './types'
import type { DeepField } from '@/types'

const DIALS = [
  ['temperature', 'settings.genTemperature'],
  ['top_p', 'settings.genTopP'],
  ['max_tokens', 'settings.genMaxTokens'],
  ['tool_budget', 'settings.genToolBudget'],
  ['context_window', 'settings.genContextWindow'],
  ['memory_max_entries', 'settings.genMemoryMax'],
  ['swarm_max_parallel', 'settings.genSwarmMax'],
] as const

export function renderGeneration(model: SettingsModel) {
  const { genDraft, i18n, setGenDraft, settings, t } = model
  const meta = settings?.generation_meta

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.generationTitle')} subtitle={t('settings.generationHint')} />
      <SettingsGroup icon={generationIcon('temperature')} title={t('settings.generationGroup')} testid="generation-group-params">
        {DIALS.map(([key, labelKey]) => {
          const bound = meta?.[key]
          const isDe = i18n?.language === 'de'
          const hint = isDe ? bound?.hint : bound?.hintEn || bound?.hint
          const field: DeepField = {
            key,
            type: 'number',
            label: t(labelKey),
            labelEn: t(labelKey),
            default: bound?.default ?? null,
            value: genDraft[key] ?? '',
            min: bound?.min,
            max: bound?.max ?? undefined,
          }
          return (
            <SettingsRow
              key={key}
              icon={generationIcon(key)}
              title={field.label}
              description={hint}
              testid={`generation-row-${key}`}
            >
              <SettingControl
                field={field}
                label={field.label}
                value={genDraft[key] ?? ''}
                onCommit={(next) => setGenDraft((prev) => ({ ...prev, [key]: String(next) }))}
              />
            </SettingsRow>
          )
        })}
      </SettingsGroup>

      {/* Wave 2/B4: the engine's own reasoning-effort vocabulary. Unset is the
          first choice and is exactly the request shape of every earlier version. */}
      <SettingsGroup icon={generationIcon('temperature')} title={t('settings.genReasoningGroup')} testid="generation-group-reasoning">
        <SettingsRow
          icon={generationIcon('temperature')}
          title={t('settings.genReasoning')}
          description={t('settings.genReasoningHint')}
          testid="generation-row-reasoning_effort"
        >
          <select
            aria-label={t('settings.genReasoning')}
            value={genDraft.reasoning_effort ?? ''}
            data-testid="generation-reasoning-effort"
            onChange={(event) => {
              // Read before the updater: the event is not part of the state update.
              const value = event.target.value
              setGenDraft((prev) => ({ ...prev, reasoning_effort: value }))
            }}
            className="border border-hairline-strong bg-canvas px-2 py-1 text-right font-mono text-scale-ui text-ink outline-none focus-ring transition-colors min-w-32 max-lg:min-h-11"
          >
            <option value="">{t('settings.genReasoningUnset')}</option>
            {['none', 'low', 'medium', 'high'].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </SettingsRow>
      </SettingsGroup>
    </div>
  )
}
