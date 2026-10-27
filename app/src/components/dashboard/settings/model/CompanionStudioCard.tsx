'use client'

import { useReducedMotion } from 'framer-motion'
import { useDeepBool } from '@/lib/deepSettings'
import { CompanionActor, type CompanionSpecies } from '@/components/shell/CompanionActor'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export const COMPANION_KEYS = [
  'appearance.companion_enabled',
  'appearance.companion_species',
  'appearance.companion_behavior',
  'appearance.companion_sound',
  'appearance.companion_scale',
] as const

const SPECIES: CompanionSpecies[] = ['fire_bee', 'ember_spark', 'minimal']

function valueOf(model: SettingsModel, key: string, fallback: string | number | boolean) {
  const field = (model.deepSections ?? [])
    .find((section) => section.key === 'appearance')
    ?.fields.find((entry) => entry.key === key)
  return model.deepDraft.appearance?.[key] ?? field?.value ?? field?.default ?? fallback
}

/** The live actor at the current form and scale, with the five register rows. */
export function CompanionStudioCard({ model }: { model: SettingsModel }) {
  const { t } = model
  const animationsEnabled = useDeepBool('appearance.animations_enabled', true)
  const reduced = useReducedMotion()
  const species = String(valueOf(model, 'appearance.companion_species', 'fire_bee'))
  const scale = Number(valueOf(model, 'appearance.companion_scale', 100))
  const enabled = Boolean(valueOf(model, 'appearance.companion_enabled', false))
  const form = SPECIES.includes(species as CompanionSpecies)
    ? (species as CompanionSpecies)
    : 'fire_bee'

  return (
    <div className="space-y-2" data-testid="companion-studio">
      <div
        className={`flex items-center gap-4 rounded-xl border border-hairline bg-surface p-4 ${
          enabled ? '' : 'opacity-50'
        }`}
      >
        <div className="flex w-24 shrink-0 justify-center">
          <CompanionActor
            species={form}
            scale={scale}
            still={Boolean(reduced) || !animationsEnabled}
            size="studio"
          />
        </div>
        <div className="min-w-0">
          <h4 className="text-scale-ui font-medium text-ink">
            {t('settings.companionStudioTitle')}
          </h4>
          <p className="pt-0.5 text-scale-data text-ink-faint">
            {t('settings.companionStudioHint')}
          </p>
        </div>
      </div>
      <DeepFields
        model={model}
        prefixes={['appearance.']}
        only={[...COMPANION_KEYS]}
        title={null}
        groupTestid="companion-studio-fields"
      />
    </div>
  )
}
