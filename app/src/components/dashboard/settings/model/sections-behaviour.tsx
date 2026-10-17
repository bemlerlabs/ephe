'use client'

/**
 * I6-3: the behaviour section — what Ephe does, not how it looks.
 *
 * This place did not exist before: the two chat fields hung under Appearance,
 * while the real behaviour guards (tool cap, nudge attempts, stream silence)
 * stood as constants in the core. The rows come from the register — a field
 * without a reader never shows up, and the same payload carries the group
 * titles along with their description texts.
 */
import PageHeader from '@/components/shell/PageHeader'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function BehaviourSection({ model }: { model: SettingsModel }) {
  const { t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.behaviourTitle')} subtitle={t('settings.behaviourHint')} />
      <DeepFields model={model} prefixes={['chat.']} />
    </div>
  )
}
