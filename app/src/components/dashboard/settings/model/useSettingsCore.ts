'use client'

import { useEffect } from 'react'
import {
  clearMemory,
  getMcpCatalog,
  getMcpSettings,
  getMemoryStats,
  getModelProviders,
  getPackIndex,
  getSettings,
  getHooks,
  getNetworkStatus,
  getTasks,
  healthCheck,
  listSchedules,
  listSkills,
  updateSettings,
} from '@/lib/api'
import { isJunkModel } from '@/lib/modelFilter'
import { toastBus } from '@/lib/toast'
import { engineStateOf } from './constants'
import type { useSettingsState } from './useSettingsState'

export function useSettingsCore(state: ReturnType<typeof useSettingsState>) {
  const {
    activeTab,
    currentSession,
    i18n,
    initialTab,
    isOpen,
    liveModels,
    mcpCatalog,
    mcpLoading,
    hooksLoading,
    hooksView,
    networkStatus,
    mcpServers,
    setAbout,
    setActiveTab,
    setConfirmClearMemory,
    setCustomApiKey,
    setCustomEndpoint,
    setEngineHealth,
    setEngineTesting,
    setGenDraft,
    setHooksView,
    setHooksLoading,
    setNetworkStatus,
    setLiveModels,
    setLoading,
    setMcpCatalog,
    setMcpLoading,
    setMcpServers,
    setMcpSource,
    setMcpTools,
    setMemoryScope,
    setMemoryProvider,
    setMemoryTotal,
    setOutputDraft,
    setPackIndex,
    setScheduleJobs,
    setSettings,
    setSkills,
    setTasks,
    setWorkspaceDraft,
    settings,
    skills,
    t,
    tasks,
  } = state

  useEffect(() => {
    if (!isOpen) return
    setActiveTab(initialTab ?? 'engine')
    loadSettings()
    void loadLiveModels()
    void loadMemoryStats()
  }, [isOpen, initialTab])

  useEffect(() => {
    if (!isOpen) return
    if (activeTab === 'skills' && skills === null) {
      listSkills()
        .then((r) => setSkills(r.skills))
        .catch(() => setSkills([]))
      getPackIndex()
        .then((r) => setPackIndex(r.packs))
        .catch(() => setPackIndex([]))
    }
    if (activeTab === 'cron') {
      listSchedules()
        .then((r) => setScheduleJobs(r.jobs ?? []))
        .catch(() => setScheduleJobs([]))
    }
    if (activeTab === 'tasks' && tasks === null) {
      getTasks()
        .then(setTasks)
        .catch(() => setTasks([]))
    }
    // I6-6: the network status is read as well, never guessed.
    if (activeTab === 'network' && networkStatus === null) {
      getNetworkStatus()
        .then(setNetworkStatus)
        .catch(() => setNetworkStatus(null))
    }
    // I6-4: hooks are a read page — fetch them when the section opens.
    if (activeTab === 'hooks' && hooksView === null && !hooksLoading) {
      setHooksLoading(true)
      getHooks()
        .then(setHooksView)
        .catch(() => setHooksView(null))
        .finally(() => setHooksLoading(false))
    }
    if (activeTab === 'about') {
      healthCheck()
        .then(setAbout)
        .catch(() => setAbout(null))
    }
    // The engine row states a condition, so it is read on the tab that shows it —
    // not only behind the test button, which is how a refused credential stayed
    // invisible until the user asked (measured 2026-10-10 on the render side).
    if (activeTab === 'engine') {
      void readEngineHealth()
    }
    if (activeTab === 'mcp' && mcpServers.length === 0 && !mcpLoading) {
      setMcpLoading(true)
      getMcpSettings()
        .then((r) => {
          setMcpServers(r.servers ?? [])
          setMcpSource(r.source ?? '')
          setMcpTools(r.tools ?? [])
        })
        .catch(() => {})
        .finally(() => setMcpLoading(false))
    }
    // E3c: load the catalog once when the MCP tab opens (static data).
    if (activeTab === 'mcp' && mcpCatalog === null) {
      getMcpCatalog()
        .then((r) => setMcpCatalog(r.entries ?? []))
        .catch(() => setMcpCatalog([]))
    }
  }, [isOpen, activeTab, skills, tasks])

  async function loadSettings() {
    try {
      setLoading(true)
      const data = await getSettings()
      setSettings(data)
      // Root-Cause #2: the endpoint was editable only for custom_ollama — with
      // the active openai_compatible/vLLM engine customEndpoint stayed empty and
      // the URL block never rendered. One condition widened, flow stays shared.
      if (data.provider.type === 'custom_ollama' || data.provider.type === 'openai_compatible') {
        setCustomEndpoint(data.provider.endpoint || '')
        // The stored key never travels back: the block already shows whether one is held
        // (`engineHealth.engine_key_configured`, keyHeld in sections-engine.tsx), and a
        // save that carries no field keeps the stored key.
        setCustomApiKey('')
      }
      setWorkspaceDraft(data.workspace_dir || '')
      setOutputDraft(data.output_dir || '')
      // Wave 5: draft of the deep parameters, filled out of the generation block.
      const g = data.generation || {}
      setGenDraft({
        temperature: g.temperature != null ? String(g.temperature) : '',
        top_p: g.top_p != null ? String(g.top_p) : '',
        max_tokens: g.max_tokens != null ? String(g.max_tokens) : '',
        tool_budget: g.tool_budget != null ? String(g.tool_budget) : '',
        context_window: g.context_window != null ? String(g.context_window) : '',
        memory_max_entries: g.memory_max_entries != null ? String(g.memory_max_entries) : '',
      })
    } catch {
      // A read that failed says nothing about the engine, so nothing is seeded into the
      // model field: a tag written here would render as a choice the user never made.
      setSettings({
        provider: { type: 'local_ollama', model: '' },
        memory_enabled: true,
        language: 'de',
      })
    } finally {
      setLoading(false)
    }
  }

  async function loadLiveModels() {
    try {
      const res = await getModelProviders()
      const opts = res.local_model_options?.length
        ? res.local_model_options
        : (res.local_models ?? []).map((name) => ({ name }))
      // F-J (t5 audit): do not offer "test"/embedding models as a chat model.
      setLiveModels(opts.filter((m) => !isJunkModel(m.name)))
    } catch {
      setLiveModels([])
    }
  }

  async function loadMemoryStats() {
    try {
      const s = await getMemoryStats()
      setMemoryTotal(s.total)
      setMemoryScope(s.scope ?? null)
      setMemoryProvider(s.provider ?? null)
    } catch {
      setMemoryTotal(null)
    }
  }

  async function clearMemoryAll() {
    try {
      await clearMemory()
      setMemoryTotal(0)
      setConfirmClearMemory(false)
      toastBus.success(t('settings.memoryCleared'))
    } catch {
      toastBus.error(t('settings.memoryClearFailed'))
    }
  }

  async function selectLanguage(code: string) {
    setSettings((prev) => (prev ? { ...prev, language: code } : prev))
    try {
      await i18n?.changeLanguage(code)
      await updateSettings({ language: code })
      toastBus.success(t('settings.languageApplied'), code === 'de' ? 'Deutsch' : 'English')
    } catch {
      toastBus.error(t('settings.languageApplyFailed'))
    }
  }

  /** What the running backend reports about its own engine, stored for the row. */
  async function readEngineHealth() {
    try {
      const result = await healthCheck()
      setEngineHealth(result)
      return result
    } catch {
      setEngineHealth(null)
      return null
    }
  }

  async function checkHealth() {
    setEngineTesting(true)
    try {
      const result = await readEngineHealth()
      if (!result) {
        toastBus.error(t('settings.healthFail'))
        return
      }
      // F-02: the toast must show engine reality, not just backend reachability.
      // W18/A5: three-valued — "busy" (the engine misses the answer deadline
      // right now) is not the same as "unreachable" (the engine really is down).
      const state = engineStateOf(result)
      // A fourth fact the three states cannot carry: the engine answered and
      // refused the credential. Calling that "unreachable" sends the user to the
      // network tab for a problem the key field on this tab fixes. The toast names
      // what happened; the row behind it carries the action, so the sentence is
      // not doubled here.
      if (result.engine_key_challenge) {
        toastBus.error(
          t('settings.engineKeyChallenge'),
          `${result.active_provider} · ${result.active_model}`,
        )
        return
      }
      const detail = `${result.active_provider} · ${result.active_model} · ${t(
        `settings.engineState.${state}`,
      )}`
      if (state === 'ok') {
        toastBus.success(t('settings.healthOk'), detail)
      } else if (state === 'busy') {
        toastBus.error(t('settings.engineBusy'), detail)
      } else {
        toastBus.error(t('settings.healthEngineDown'), detail)
      }
    } finally {
      setEngineTesting(false)
    }
  }

  // G5: live models from the engine + the custom option.
  // F-05: the static Ollama fallback (gemma4/LLaMA/Mistral) shows ONLY for
  // Ollama providers — under openai_compatible those were models the engine
  // does not have at all (misleading). When the active model is missing
  // from the live list (e.g. the engine is briefly offline) it is still
  // shown and marked as a chip — the user always sees what is really active.
  const customOption = { id: 'custom', label: 'Custom Ollama', descKey: 'settings.customModelDesc' }
  const providerType = settings?.provider.type
  const isOllamaFamily = providerType !== 'openai_compatible'
  const liveChips = liveModels.map((m) => ({
    id: m.name,
    label: m.label || m.name,
    // Finding 2026-10-01: the old fallback "Engine" stood on EVERY card without
    // metadata — a meaningless label. Leave it out entirely without family/size.
    desc: [m.family, m.parameter_size].filter(Boolean).join(' · ') || undefined,
  }))
  const activeModel = settings?.provider.model
  if (
    activeModel &&
    providerType === 'openai_compatible' &&
    !liveChips.some((c) => c.id === activeModel)
  ) {
    liveChips.unshift({ id: activeModel, label: activeModel, desc: t('settings.activeModelChip') })
  }
  const displayModels: Array<{ id: string; label: string; desc?: string; descKey?: string }> = [
    ...liveChips,
    ...(isOllamaFamily ? [customOption] : []),
  ]

  const artifacts = (currentSession?.messages ?? [])
    .flatMap((m) => m.activities ?? [])
    .filter((a): a is typeof a & { path: string } => Boolean(a.path))

  return {
    loadSettings,
    loadLiveModels,
    loadMemoryStats,
    clearMemoryAll,
    selectLanguage,
    checkHealth,
    customOption,
    providerType,
    isOllamaFamily,
    liveChips,
    activeModel,
    displayModels,
    artifacts,
  }
}
