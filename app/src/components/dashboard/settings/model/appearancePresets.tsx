'use client'

import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { SegmentedControl } from '@/components/shell/SettingControl'
import type { SettingsModel } from './types'

type DensityId = 'compact' | 'standard' | 'spacious'
type ReadingId = 'narrow' | 'standard' | 'wide'
type LayoutId = 'focus' | 'standard' | 'review'

const DENSITY: { id: DensityId; labelKey: string; font: number; chat: number }[] = [
  { id: 'compact', labelKey: 'settings.presetDensityCompact', font: 90, chat: 90 },
  { id: 'standard', labelKey: 'settings.presetDensityStandard', font: 100, chat: 100 },
  { id: 'spacious', labelKey: 'settings.presetDensitySpacious', font: 110, chat: 110 },
]

const READING: { id: ReadingId; labelKey: string; width: number }[] = [
  { id: 'narrow', labelKey: 'settings.presetReadingNarrow', width: 640 },
  { id: 'standard', labelKey: 'settings.presetReadingStandard', width: 768 },
  { id: 'wide', labelKey: 'settings.presetReadingWide', width: 1024 },
]

const LAYOUT: { id: LayoutId; labelKey: string; font: number; chat: number; width: number }[] = [
  { id: 'focus', labelKey: 'settings.presetLayoutFocus', font: 90, chat: 90, width: 640 },
  { id: 'standard', labelKey: 'settings.presetLayoutStandard', font: 100, chat: 100, width: 768 },
  { id: 'review', labelKey: 'settings.presetLayoutReview', font: 110, chat: 110, width: 1024 },
]

const FONT = 'appearance.font_scale'
const CHAT = 'appearance.chat_font_scale'
const WIDTH = 'appearance.reading_width'

function current(model: SettingsModel, key: string, fallback: number): number {
  const field = (model.deepSections ?? [])
    .find((section) => section.key === 'appearance')
    ?.fields.find((entry) => entry.key === key)
  const value = model.deepDraft?.appearance?.[key]
  const resolved = value ?? field?.value ?? field?.default ?? fallback
  return typeof resolved === 'number' ? resolved : Number(resolved)
}

function matchDensity(model: SettingsModel) {
  const font = current(model, FONT, 100)
  const chat = current(model, CHAT, 100)
  return DENSITY.find((preset) => preset.font === font && preset.chat === chat) ?? null
}

function matchReading(model: SettingsModel) {
  const width = current(model, WIDTH, 768)
  return READING.find((preset) => preset.width === width) ?? null
}

function matchLayout(model: SettingsModel) {
  const font = current(model, FONT, 100)
  const chat = current(model, CHAT, 100)
  const width = current(model, WIDTH, 768)
  return (
    LAYOUT.find(
      (preset) => preset.font === font && preset.chat === chat && preset.width === width,
    ) ?? null
  )
}

export function AppearancePresets({ model }: { model: SettingsModel }) {
  const { t, setDeepField } = model
  const density = matchDensity(model)
  const reading = matchReading(model)
  const layout = matchLayout(model)
  const custom = t('settings.presetCustom')

  return (
    <SettingsGroup
      title={t('settings.presetsTitle')}
      description={t('settings.presetsHint')}
      testid="appearance-presets"
    >
      <SettingsRow title={t('settings.presetDensity')} testid="appearance-preset-density">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <SegmentedControl
            label={t('settings.presetDensity')}
            value={density?.id ?? null}
            options={DENSITY.map((preset) => ({ id: preset.id, label: t(preset.labelKey) }))}
            onChange={(id) => {
              const preset = DENSITY.find((entry) => entry.id === id)
              if (!preset) return
              setDeepField('appearance', FONT, preset.font)
              setDeepField('appearance', CHAT, preset.chat)
            }}
            testid="appearance-preset-density-control"
          />
          {!density && (
            <span
              data-testid="appearance-preset-density-custom"
              className="text-scale-data text-ink-faint"
            >
              {custom}
            </span>
          )}
        </div>
      </SettingsRow>
      <SettingsRow title={t('settings.presetReading')} testid="appearance-preset-reading">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <SegmentedControl
            label={t('settings.presetReading')}
            value={reading?.id ?? null}
            options={READING.map((preset) => ({ id: preset.id, label: t(preset.labelKey) }))}
            onChange={(id) => {
              const preset = READING.find((entry) => entry.id === id)
              if (!preset) return
              setDeepField('appearance', WIDTH, preset.width)
            }}
            testid="appearance-preset-reading-control"
          />
          {!reading && (
            <span
              data-testid="appearance-preset-reading-custom"
              className="text-scale-data text-ink-faint"
            >
              {custom}
            </span>
          )}
        </div>
      </SettingsRow>
      <SettingsRow title={t('settings.presetLayout')} testid="appearance-preset-layout">
        <div className="flex flex-wrap items-center justify-end gap-2">
          <SegmentedControl
            label={t('settings.presetLayout')}
            value={layout?.id ?? null}
            options={LAYOUT.map((preset) => ({ id: preset.id, label: t(preset.labelKey) }))}
            onChange={(id) => {
              const preset = LAYOUT.find((entry) => entry.id === id)
              if (!preset) return
              setDeepField('appearance', FONT, preset.font)
              setDeepField('appearance', CHAT, preset.chat)
              setDeepField('appearance', WIDTH, preset.width)
            }}
            testid="appearance-preset-layout-control"
          />
          {!layout && (
            <span
              data-testid="appearance-preset-layout-custom"
              className="text-scale-data text-ink-faint"
            >
              {custom}
            </span>
          )}
        </div>
      </SettingsRow>
    </SettingsGroup>
  )
}
