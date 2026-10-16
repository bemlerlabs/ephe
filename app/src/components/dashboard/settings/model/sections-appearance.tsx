'use client'

/**
 * I3-V5: the appearance section — before this it did not exist as a place.
 *
 * The theme hung as a button on the chat header (localStorage 'ephe.theme'), the
 * font size and the animations sat in the expert box, timestamps and the thinking
 * phase were nowhere to find. They come together here: what you see, in one place,
 * in the row form of the rest of the settings.
 */
import { useState } from 'react'
import { MoonStar, SunMedium } from 'lucide-react'
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import { applyTheme, getStoredTheme, type ThemeMode } from '@/lib/theme'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function AppearanceSection({ model }: { model: SettingsModel }) {
  const { t } = model
  const [theme, setTheme] = useState<ThemeMode>(() => getStoredTheme())

  const pick = (next: ThemeMode) => {
    applyTheme(next)
    setTheme(next)
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.appearanceTitle')} subtitle={t('settings.appearanceHint')} />
      <SettingsGroup icon={MoonStar} title={t('settings.appearanceGroupTheme')}>
        <SettingsRow
          icon={theme === 'dark' ? MoonStar : SunMedium}
          title={t('settings.appearanceTheme')}
          description={t('settings.appearanceThemeHint')}
          testid="appearance-row-theme"
        >
          <div
            role="radiogroup"
            aria-label={t('settings.appearanceTheme')}
            className="flex rounded-lg bg-surface p-0.5 gap-0.5"
          >
            {(['dark', 'light'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                role="radio"
                aria-checked={theme === mode}
                data-testid={`appearance-theme-${mode}`}
                onClick={() => pick(mode)}
                className={`rounded-md px-3 py-1 text-ui-xs font-medium transition-colors ${
                  theme === mode
                    ? 'bg-brand/25 text-brand'
                    : 'text-ink-faint hover:text-foreground/80'
                }`}
              >
                {t(`settings.appearanceTheme.${mode}`)}
              </button>
            ))}
          </div>
        </SettingsRow>
      </SettingsGroup>
      {/* I6-3: the chat fields moved out to the behaviour section — what stays
          here is what you see. */}
      <DeepFields model={model} prefixes={['appearance.']} />
    </div>
  )
}
