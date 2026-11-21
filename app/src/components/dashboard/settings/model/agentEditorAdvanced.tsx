'use client'

import { Archive, Loader2, Play, Plus, ShieldCheck, Trash2 } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import type { AgentAccess, AgentRule, AgentRun, AgentTestResult, AgentTool } from '@/lib/api'
import { BUTTON, FIELD, PRIMARY, type T } from './agentShared'

export function AgentRules({
  rules,
  tools,
  readOnly,
  t,
  onAdd,
  onUpdate,
  onRemove,
}: {
  rules: AgentRule[]
  tools: AgentTool[]
  readOnly: boolean
  t: T
  onAdd: () => void
  onUpdate: (index: number, patch: Partial<AgentRule>) => void
  onRemove: (index: number) => void
}) {
  return (
    <SettingsGroup
      icon={ShieldCheck}
      title={t('settings.agentPermissions')}
      description={t('settings.agentPermissionsHint')}
      action={
        <button
          type="button"
          className={BUTTON}
          onClick={onAdd}
          disabled={readOnly || !tools.length}
          data-testid="agent-add-rule"
        >
          <Plus className="h-3.5 w-3.5" /> {t('settings.agentAddRule')}
        </button>
      }
      testid="agent-group-rules"
    >
      <div className="space-y-2 px-4 py-3">
        {rules.length === 0 && <p className="text-ui-xs text-ink-faint">—</p>}
        {rules.map((rule, index) => (
          <div
            key={index}
            className="flex flex-wrap items-center gap-2"
            data-testid={`agent-rule-${index}`}
          >
            <select
              className={`${FIELD} w-auto min-w-32`}
              value={rule.tool}
              onChange={(e) => onUpdate(index, { tool: e.target.value })}
              disabled={readOnly}
              aria-label={t('settings.agentRuleTool')}
            >
              {tools.map((tool) => (
                <option key={tool.name} value={tool.name}>
                  {tool.name}
                </option>
              ))}
            </select>
            <select
              className={`${FIELD} w-auto min-w-24`}
              value={rule.access}
              onChange={(e) => onUpdate(index, { access: e.target.value as AgentAccess })}
              disabled={readOnly}
              aria-label={t('settings.agentRuleAccess')}
            >
              <option value="allow">allow</option>
              <option value="ask">ask</option>
              <option value="block">block</option>
            </select>
            <input
              className={`${FIELD} min-w-32 flex-1`}
              value={rule.purpose}
              maxLength={200}
              placeholder={t('settings.agentRulePurpose')}
              onChange={(e) => onUpdate(index, { purpose: e.target.value })}
              disabled={readOnly}
              aria-label={t('settings.agentRulePurpose')}
            />
            <button
              type="button"
              className={BUTTON}
              onClick={() => onRemove(index)}
              disabled={readOnly}
              aria-label={t('settings.agentRuleRemove')}
              data-testid={`agent-rule-remove-${index}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </SettingsGroup>
  )
}

export function AgentTest({
  prompt,
  setPrompt,
  running,
  result,
  canRun,
  readOnly,
  t,
  onRun,
}: {
  prompt: string
  setPrompt: (value: string) => void
  running: boolean
  result: AgentTestResult | null
  canRun: boolean
  readOnly: boolean
  t: T
  onRun: () => void
}) {
  return (
    <SettingsGroup
      icon={Play}
      title={t('settings.agentTest')}
      description={t('settings.agentTestHint')}
      testid="agent-group-test"
    >
      <div className="space-y-2 px-4 py-3">
        <textarea
          className={`${FIELD} min-h-20 resize-y`}
          value={prompt}
          maxLength={4000}
          placeholder={t('settings.agentTestPlaceholder')}
          onChange={(e) => setPrompt(e.target.value)}
          data-testid="agent-test-prompt"
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={PRIMARY}
            onClick={onRun}
            disabled={!canRun || !prompt.trim() || running || readOnly}
            data-testid="agent-test-run"
          >
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {running ? t('settings.agentTestRunning') : t('settings.agentTestRun')}
          </button>
          {!canRun && <span className="text-ui-2xs text-ink-faint">{t('settings.agentSave')}</span>}
        </div>
        {result && (
          <div className="glass-reading rounded-xl p-3" data-testid="agent-test-result">
            <p className="text-ui-2xs text-ink-faint">
              {result.status} · {result.model || '—'} · {result.model_source}
            </p>
            <pre className="mt-1 whitespace-pre-wrap break-words text-ui-xs text-foreground/90">
              {result.report}
            </pre>
          </div>
        )}
      </div>
    </SettingsGroup>
  )
}

export function AgentRuns({ runs, t }: { runs: AgentRun[]; t: T }) {
  return (
    <SettingsGroup icon={Archive} title={t('settings.agentRuns')} testid="agent-group-runs">
      <div className="space-y-1.5 px-4 py-3">
        {runs.length === 0 && (
          <p className="text-ui-xs text-ink-faint">{t('settings.agentNoRuns')}</p>
        )}
        {runs.map((run) => (
          <div
            key={run.run_id}
            data-testid={`agent-run-${run.run_id}`}
            className="flex flex-wrap items-center gap-2 text-ui-xs text-ink-soft"
          >
            <span className="font-mono text-ui-2xs text-ink-faint">{run.finished_at}</span>
            <span>{run.status}</span>
            <span className="text-ink-faint">
              {run.model || '—'} · {run.model_source}
            </span>
            <span className="text-ink-faint">
              {run.duration_ms} ms · {run.tool_calls} tools · {run.source}
            </span>
          </div>
        ))}
      </div>
    </SettingsGroup>
  )
}
