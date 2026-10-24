'use client'

import { Bot, Check, ShieldCheck } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import type { AgentRecord, AgentTool } from '@/lib/api'
import { BUTTON, DEFAULT_TOOLS, Field, FIELD, type T } from './agentShared'

export function AgentBasics({
  draft,
  set,
  modelId,
  setModelId,
  models,
  tools,
  readOnly,
  t,
}: {
  draft: Partial<AgentRecord>
  set: (patch: Partial<AgentRecord>) => void
  modelId: string
  setModelId: (value: string) => void
  models: string[]
  tools: AgentTool[]
  readOnly: boolean
  t: T
}) {
  return (
    <>
      <SettingsGroup icon={Bot} title={t('settings.agentGroupBasic')} testid="agent-group-basic">
        <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
          <Field label={t('settings.agentName')}>
            <input
              className={FIELD}
              value={draft.name ?? ''}
              maxLength={80}
              onChange={(e) => set({ name: e.target.value })}
              disabled={readOnly}
              data-testid="agent-name"
            />
          </Field>
          <Field label={t('settings.agentDescription')}>
            <input
              className={FIELD}
              value={draft.description ?? ''}
              maxLength={500}
              onChange={(e) => set({ description: e.target.value })}
              disabled={readOnly}
              data-testid="agent-description"
            />
          </Field>
          <div className="sm:col-span-2">
            <Field
              label={t('settings.agentInstructions')}
              hint={t('settings.agentInstructionsHint')}
            >
              <textarea
                className={`${FIELD} min-h-32 resize-y font-mono text-ui-xs leading-relaxed`}
                value={draft.instructions ?? ''}
                maxLength={32000}
                onChange={(e) => set({ instructions: e.target.value })}
                disabled={readOnly}
                data-testid="agent-instructions"
              />
            </Field>
          </div>
        </div>
      </SettingsGroup>

      <SettingsGroup
        icon={ShieldCheck}
        title={t('settings.agentModel')}
        description={t('settings.agentModelHint')}
        testid="agent-group-execution"
      >
        <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
          <Field label={t('settings.agentModel')}>
            <div className="flex gap-2">
              <input
                className={FIELD}
                value={modelId}
                list="agent-model-options"
                placeholder={t('settings.agentModelPlaceholder')}
                onChange={(e) => setModelId(e.target.value)}
                disabled={readOnly}
                data-testid="agent-model"
              />
              <button
                type="button"
                className={BUTTON}
                onClick={() => setModelId('')}
                disabled={readOnly || !modelId}
                data-testid="agent-model-auto"
              >
                {t('settings.agentModelAuto')}
              </button>
            </div>
            <datalist id="agent-model-options">
              {models.map((model) => (
                <option key={model} value={model} />
              ))}
            </datalist>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('settings.agentMaxTurns')}>
              <input
                type="number"
                min={1}
                max={24}
                className={FIELD}
                value={draft.limits?.max_turns ?? 8}
                onChange={(e) =>
                  set({
                    limits: {
                      max_turns: Number(e.target.value) || 1,
                      timeout: draft.limits?.timeout ?? 180,
                    },
                  })
                }
                disabled={readOnly}
                data-testid="agent-max-turns"
              />
            </Field>
            <Field label={t('settings.agentTimeout')}>
              <input
                type="number"
                min={30}
                max={900}
                step={10}
                className={FIELD}
                value={draft.limits?.timeout ?? 180}
                onChange={(e) =>
                  set({
                    limits: {
                      max_turns: draft.limits?.max_turns ?? 8,
                      timeout: Number(e.target.value) || 30,
                    },
                  })
                }
                disabled={readOnly}
                data-testid="agent-timeout"
              />
            </Field>
          </div>
        </div>
      </SettingsGroup>

      <SettingsGroup
        icon={Bot}
        title={t('settings.agentTools')}
        description={t('settings.agentToolsHint')}
        testid="agent-group-tools"
      >
        <div className="flex flex-wrap gap-2 px-4 py-3">
          {tools.map((tool) => {
            const active = (draft.tools ?? DEFAULT_TOOLS).includes(tool.name)
            return (
              <button
                key={tool.name}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  const current = draft.tools ?? DEFAULT_TOOLS
                  set({
                    tools: active
                      ? current.filter((name) => name !== tool.name)
                      : [...current, tool.name],
                  })
                }}
                disabled={readOnly}
                data-testid={`agent-tool-${tool.name}`}
                className={`focus-ring inline-flex min-h-8 items-center gap-1.5 rounded-full border px-2.5 py-1 text-ui-xs transition-colors pointer-coarse:min-h-11 ${
                  active
                    ? 'border-brand/40 bg-brand/15 text-brand-deep'
                    : 'border-control bg-surface text-ink-soft hover:text-ink'
                }`}
              >
                {active && <Check className="h-3 w-3" />}
                <span className="font-mono">{tool.name}</span>
              </button>
            )
          })}
        </div>
      </SettingsGroup>
    </>
  )
}
