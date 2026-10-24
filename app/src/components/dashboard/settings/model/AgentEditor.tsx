'use client'

import { useCallback, useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'

import { toastBus } from '@/lib/toast'
import { createAgent, listAgentRuns, testAgent, updateAgent } from '@/lib/api'
import type { AgentRecord, AgentRule, AgentRun, AgentTestResult, AgentTool } from '@/lib/api'
import { AgentBasics } from './agentEditorFields'
import { AgentRuns, AgentRules, AgentTest } from './agentEditorAdvanced'
import { blankAgent, BUTTON, originLabel, PRIMARY, type T } from './agentShared'

export function AgentEditor({
  initial,
  tools,
  models,
  provider,
  t,
  onClose,
  onSaved,
}: {
  initial: AgentRecord | null
  tools: AgentTool[]
  models: string[]
  provider: string
  t: T
  onClose: () => void
  onSaved: (record: AgentRecord) => void
}) {
  const [draft, setDraft] = useState<Partial<AgentRecord>>(() =>
    initial ? { ...initial } : blankAgent(),
  )
  const [modelId, setModelId] = useState(initial?.model?.model ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [testPrompt, setTestPrompt] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<AgentTestResult | null>(null)
  const [runs, setRuns] = useState<AgentRun[]>([])
  const readOnly = Boolean(initial?.read_only)

  const loadRuns = useCallback(async (id: string) => {
    try {
      setRuns((await listAgentRuns(id)).runs)
    } catch {
      setRuns([])
    }
  }, [])

  useEffect(() => {
    if (initial?.id) void loadRuns(initial.id)
  }, [initial?.id, loadRuns])

  const set = (patch: Partial<AgentRecord>) => setDraft((prev) => ({ ...prev, ...patch }))

  const rules = draft.permissions?.rules ?? []
  const setRules = (next: AgentRule[]) =>
    set({ permissions: { approval: draft.permissions?.approval ?? 'inherit', rules: next } })

  const addRule = () => {
    const first = tools[0]?.name
    if (!first) return
    setRules([...rules, { tool: first, access: 'block', purpose: '' }])
  }
  const updateRule = (index: number, patch: Partial<AgentRule>) =>
    setRules(rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)))
  const removeRule = (index: number) => setRules(rules.filter((_, i) => i !== index))

  const save = async () => {
    setError('')
    if (!(draft.name ?? '').trim()) {
      setError(t('settings.agentName'))
      return
    }
    if (!(draft.tools ?? []).length) {
      setError(t('settings.agentToolsHint'))
      return
    }
    setSaving(true)
    try {
      const payload: Partial<AgentRecord> = {
        name: draft.name,
        description: draft.description,
        instructions: draft.instructions,
        tools: draft.tools,
        model: modelId.trim()
          ? { provider: provider || null, model: modelId.trim(), tier: 'auto' }
          : null,
        permissions: draft.permissions,
        limits: draft.limits,
        enabled: draft.enabled,
      }
      const saved =
        initial && initial.id
          ? await updateAgent(initial.id, payload, initial.etag ?? '')
          : await createAgent(payload)
      toastBus.success(t('settings.agentSaved'))
      onSaved(saved)
    } catch (err) {
      const detail = err instanceof Error ? err.message : ''
      setError(detail || t('settings.agentSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const runTest = async () => {
    if (!initial?.id || !testPrompt.trim()) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testAgent(initial.id, testPrompt.trim())
      setTestResult(result)
      await loadRuns(initial.id)
    } catch (err) {
      toastBus.error(t('settings.agentTestFailed'), err instanceof Error ? err.message : undefined)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-4" data-testid="agent-editor">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-xl font-semibold text-foreground/95">
            {(draft.name ?? '').trim() || t('settings.agentNewName')}
          </h3>
          <p className="mt-0.5 text-ui-xs text-ink-faint">
            {originLabel(initial?.origin ?? 'local', t)}
            {readOnly && ` · ${t('settings.agentReadOnly')}`}
          </p>
        </div>
        <button type="button" className={BUTTON} onClick={onClose} data-testid="agent-cancel">
          {t('settings.agentCancel')}
        </button>
        <button
          type="button"
          className={PRIMARY}
          onClick={() => void save()}
          disabled={saving || readOnly}
          data-testid="agent-save"
        >
          {saving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          )}
          {saving ? t('settings.agentSaving') : t('settings.agentSave')}
        </button>
      </div>
      {error && (
        <p role="alert" data-testid="agent-error" className="text-ui-xs text-status-danger">
          {error}
        </p>
      )}

      <AgentBasics
        draft={draft}
        set={set}
        modelId={modelId}
        setModelId={setModelId}
        models={models}
        tools={tools}
        readOnly={readOnly}
        t={t}
      />
      <AgentRules
        rules={rules}
        tools={tools}
        readOnly={readOnly}
        t={t}
        onAdd={addRule}
        onUpdate={updateRule}
        onRemove={removeRule}
      />
      <AgentTest
        prompt={testPrompt}
        setPrompt={setTestPrompt}
        running={testing}
        result={testResult}
        canRun={Boolean(initial?.id)}
        readOnly={readOnly}
        t={t}
        onRun={() => void runTest()}
      />
      {initial?.id && <AgentRuns runs={runs} t={t} />}
    </div>
  )
}
