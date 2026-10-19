'use client'

/**
 * I6-3: the behaviour section — what Ephe does, not how it looks.
 *
 * This place did not exist before: the two chat fields hung under Appearance,
 * while the real behaviour guards (tool cap, nudge attempts, stream silence)
 * stood as constants in the core. The rows come from the register — a field
 * without a reader never shows up, and the same payload carries the group
 * titles along with their description texts.
 *
 * Wave 2 (B1): the custom-instruction layer is edited here, above the rows. It gets
 * a full-width card because it holds sentences where the register rows hold a value;
 * the section's one save footer writes it like every other field here.
 */
import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import { DeepFields } from './deepFields'
import type { SettingsModel } from './types'

function CustomInstructionsCard({ model }: { model: SettingsModel }) {
  const { deepDraft, deepSections, i18n, setDeepField, t } = model
  const isDe = i18n?.language === 'de'
  const field = (deepSections ?? [])
    .flatMap((section) => section.fields)
    .find((entry) => entry.key === 'chat.custom_instructions')
  const cap = field?.maxChars ?? 4000
  const value = String(deepDraft.chat?.['chat.custom_instructions'] ?? field?.value ?? '')
  const label = isDe ? 'Eigene Anweisungen' : 'Custom instructions'

  return (
    <SettingsGroup
      title={t('settings.customInstructionsTitle')}
      description={t('settings.customInstructionsHint')}
      testid="custom-instructions-group"
    >
      <div className="space-y-2 p-3">
        <textarea
          aria-label={label}
          value={value}
          onChange={(event) =>
            setDeepField('chat', 'chat.custom_instructions', event.target.value.slice(0, cap))
          }
          rows={6}
          spellCheck={false}
          placeholder={t('settings.customInstructionsPlaceholder')}
          data-testid="custom-instructions-input"
          className="w-full glass-control rounded-xl p-3 text-ui-input font-mono text-foreground/90 outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 resize-y leading-relaxed"
        />
        <span
          className="block text-ui-xs font-mono text-ink-faint"
          data-testid="custom-instructions-count"
        >
          {value.length} / {cap}
        </span>
      </div>
    </SettingsGroup>
  )
}

export function BehaviourSection({ model }: { model: SettingsModel }) {
  const { t } = model

  return (
    <div className="space-y-4">
      <PageHeader title={t('settings.behaviourTitle')} subtitle={t('settings.behaviourHint')} />
      <CustomInstructionsCard model={model} />
      <DeepFields model={model} prefixes={['chat.']} />
    </div>
  )
}
