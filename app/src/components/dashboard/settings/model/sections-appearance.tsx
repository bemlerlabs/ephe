'use client'

/**
 * I3-V5: the appearance section — before this it did not exist as a place.
 *
 * The font size and the animations sat in the expert box, timestamps and the thinking
 * phase were nowhere to find, and the light or dark choice hung as a button on the chat
 * header. They came together here: what you see, in one place, in the row form of the rest
 * of the settings. The header's theme button went with the paper ground it switched
 * (owner decision 2026-10-19: the forest is the only theme the product ships), so what
 * remains is the register's own appearance block.
 */
import PageHeader from '@/components/shell/PageHeader'
import { AppearancePresets } from './appearancePresets'
import { AppearanceProfile } from './AppearanceProfileSection'
import { CompanionStudioCard, COMPANION_KEYS } from './CompanionStudioCard'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function AppearanceSection({ model }: { model: SettingsModel }) {
  const { t, instantStatus, instantError } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.appearanceTitle')} subtitle={t('settings.appearanceHint')} />
      {/* The bundles sit above the raw rows and write only their own keys. */}
      <AppearancePresets model={model} />
      <CompanionStudioCard model={model} />
      {/* I6-3: the chat fields moved out to the behaviour section — what stays
          here is what you see. The five companion rows live in the studio. */}
      <DeepFields model={model} prefixes={['appearance.']} exclude={[...COMPANION_KEYS]} />
      <AppearanceProfile model={model} />
      {instantStatus !== 'idle' && (
        <p
          role={instantStatus === 'error' ? 'alert' : 'status'}
          data-testid="appearance-instant-status"
          className={`px-1 text-scale-data ${
            instantStatus === 'error' ? 'text-status-danger' : 'text-ink-faint'
          }`}
        >
          {instantStatus === 'saving' && t('settings.appearanceSaving')}
          {instantStatus === 'saved' && t('settings.appearanceSaved')}
          {instantStatus === 'error' &&
            `${t('settings.appearanceSaveFailed')}${instantError ? `: ${instantError}` : ''}`}
        </p>
      )}
    </div>
  )
}
