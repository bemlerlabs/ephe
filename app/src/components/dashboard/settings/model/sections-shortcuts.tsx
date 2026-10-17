'use client'

/**
 * I6-5: the keyboard-shortcut area.
 *
 * `SHORTCUTS` in app/src/lib/shortcuts.ts is the only table since P2-4: the help
 * overlay renders its rows from it, ChatLayout attaches the handlers to the same
 * IDs. This area shows exactly that table — in the key notation of the platform
 * Ephe runs on.
 *
 * Not built: rebinding. No handler reads a personal binding, there is no file for
 * it and no conflict check. A field that writes a binding nobody reads would be
 * the first dead button of this area.
 */
import { Keyboard, LayoutGrid, SquareTerminal } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { SHORTCUTS, isMacPlatform, renderKeys } from '@/lib/shortcuts'
import type { SettingsModel } from './types'

const GROUPS = [
  { key: 'navigation', icon: LayoutGrid },
  { key: 'composer', icon: SquareTerminal },
  { key: 'global', icon: Keyboard },
] as const

export function ShortcutsSection({ model }: { model: SettingsModel }) {
  const { t } = model
  const isMac = isMacPlatform()

  return (
    <div className="space-y-4">
      <PageHeader title={t('shortcuts.title')} subtitle={t('settings.shortcutsHint')} />
      {GROUPS.map((group) => {
        const rows = SHORTCUTS.filter((s) => s.group === group.key)
        if (rows.length === 0) return null
        return (
          <SettingsGroup
            key={group.key}
            icon={group.icon}
            title={t(`settings.shortcutsGroup.${group.key}`)}
            testid={`shortcuts-group-${group.key}`}
          >
            {rows.map((s) => (
              <SettingsRow
                key={s.id}
                icon={group.icon}
                title={renderKeys(s.keys, isMac)}
                description={t(s.labelKey, { defaultValue: s.fallback ?? s.labelKey })}
                testid={`shortcuts-row-${s.id}`}
              />
            ))}
          </SettingsGroup>
        )
      })}
      <p className="text-ui-xs text-ink-faint" data-testid="shortcuts-fixed-note">
        {t('settings.shortcutsFixed')}
      </p>
    </div>
  )
}
