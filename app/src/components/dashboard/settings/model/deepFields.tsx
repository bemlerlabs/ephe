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
import SettingControl from '@/components/shell/SettingControl'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { fieldIcon, sectionIcon } from '@/components/shell/settingsIcons'
import { deepFieldsOf } from './deepRegister'
import type { SettingsModel } from './types'

export function DeepFields({ model, prefixes }: { model: SettingsModel; prefixes: string[] }) {
  const { deepDraft, deepSections, i18n, setDeepField, t } = model
  const isDe = i18n?.language === 'de'
  const groups = deepFieldsOf(deepSections, prefixes)
  if (groups.length === 0) return null

  return (
    <div className="space-y-4 pt-2" data-testid="deep-fields">
      {groups.map((sec) => (
        <SettingsGroup
          key={sec.key}
          icon={sectionIcon(sec.key)}
          title={t(`settings.deepSection.${sec.key}`, { defaultValue: sec.key })}
          testid={`deep-section-${sec.key}`}
        >
          {sec.fields.map((f) => {
            // A multiline field is not a row: it is edited in the section's own
            // card, where a textarea and a character counter have room.
            if (f.multiline) return null
            const value = deepDraft[sec.key]?.[f.key] ?? f.value ?? f.default ?? ''
            const label = isDe ? f.label : f.labelEn || f.label
            const hint = isDe ? f.hint : f.hintEn || f.hint
            return (
              <SettingsRow
                key={f.key}
                icon={fieldIcon(f.key, f.type)}
                title={label}
                description={hint}
                testid={`deep-row-${f.key}`}
              >
                <SettingControl
                  field={f}
                  label={label}
                  value={value}
                  onCommit={(next) => setDeepField(sec.key, f.key, next)}
                />
              </SettingsRow>
            )
          })}
        </SettingsGroup>
      ))}
    </div>
  )
}
