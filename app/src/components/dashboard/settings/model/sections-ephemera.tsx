'use client'

/**
 * R1 (WP7): the ephemerality section.
 *
 * Before: a cell's lifetime stood as a constant in `core/ephemeral_cell.py`, and
 * nobody decided whether a deleted session took its workbook along — it simply
 * did not happen. Both are now a control with a reader, and this section shows
 * exactly those two rows.
 *
 * What is not here is deliberate: the cell caps (Fuel, Memory, disk) are measured
 * in `code-exec`, not set, and the memory ceiling lives in the generation block
 * of engine.json. A third field for the same cap would be a second number for the
 * same thing.
 */
import PageHeader from '@/components/shell/PageHeader'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

export function EphemeraSection({ model }: { model: SettingsModel }) {
  const { t } = model
  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.ephemeraTitle')} subtitle={t('settings.ephemeraSubtitle')} />
      <DeepFields model={model} prefixes={['ephemera.']} />
    </div>
  )
}
