'use client'

/**
 * I3-V5: the registry block that belongs inside a section — not in a separate
 * expert box.
 *
 * The fields stay where they are defined (core/settings_schema.py with its
 * bounds, core/settings_hints.py with its text); only the placement follows the
 * user's thinking: font and animations belong under Appearance, the time limit
 * under Engine, the plugin policy under Plugin Store. A `prefixes` call picks up
 * the matching rows.
 *
 * I6-1: the block no longer has its own save button. Two buttons carrying the
 * same word while writing different files were a false statement; the section's
 * footer button now serves both save areas.
 */
import type { DeepField } from '@/types'
import SettingControl from '@/components/shell/SettingControl'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { fieldIcon, sectionIcon } from '@/components/shell/settingsIcons'
import { deepFieldsOf } from './deepRegister'
import type { SettingsModel } from './types'

export function DeepFieldRow({
  model,
  secKey,
  field,
}: {
  model: SettingsModel
  secKey: string
  field: DeepField
}) {
  const { deepDraft, i18n, setDeepField, t } = model
  const isDe = i18n?.language === 'de'
  if (field.multiline) return null
  const value = deepDraft[secKey]?.[field.key] ?? field.value ?? field.default ?? ''
  const label = field.labelKey
    ? t(field.labelKey)
    : isDe
      ? field.label
      : field.labelEn || field.label
  const hint = field.hintKey ? t(field.hintKey) : isDe ? field.hint : field.hintEn || field.hint
  return (
    <SettingsRow
      icon={fieldIcon(field.key, field.type)}
      title={label}
      description={hint}
      testid={`deep-row-${field.key}`}
    >
      <SettingControl
        field={field}
        label={label}
        value={value}
        onCommit={(next) => setDeepField(secKey, field.key, next)}
      />
    </SettingsRow>
  )
}

export function DeepFields({
  model,
  prefixes,
  only,
  exclude,
  title,
  groupTestid,
}: {
  model: SettingsModel
  prefixes: string[]
  /** Render only these field keys (the studio card's five companion rows). */
  only?: string[]
  /** Keep these field keys out of the block (the raw rows below the studio). */
  exclude?: string[]
  /** undefined = the section's own heading; null = no heading; a string overrides it. */
  title?: string | null
  groupTestid?: string
}) {
  const { deepSections, t } = model
  const onlySet = new Set(only ?? [])
  const excludeSet = new Set(exclude ?? [])
  const groups = deepFieldsOf(deepSections, prefixes)
    .map((sec) => ({
      ...sec,
      fields: sec.fields.filter(
        (field) => (only ? onlySet.has(field.key) : true) && !excludeSet.has(field.key),
      ),
    }))
    .filter((sec) => sec.fields.length > 0)
  if (groups.length === 0) return null

  return (
    <div className="space-y-4 pt-2" data-testid="deep-fields">
      {groups.map((sec) => (
        <SettingsGroup
          key={sec.key}
          icon={sectionIcon(sec.key)}
          title={
            title === null
              ? undefined
              : (title ?? t(`settings.deepSection.${sec.key}`, { defaultValue: sec.key }))
          }
          testid={groupTestid ?? `deep-section-${sec.key}`}
        >
          {sec.fields.map((field) => (
            <DeepFieldRow key={field.key} model={model} secKey={sec.key} field={field} />
          ))}
        </SettingsGroup>
      ))}
    </div>
  )
}
