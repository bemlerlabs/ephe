'use client'

import { useEffect, useCallback, useState } from 'react'
import {
  TaskItem,
  createSchedule,
  createTask,
  deleteSchedule,
  deleteTask,
  getPlugins,
  getSettings,
  getTasks,
  listSchedules,
  saveSections,
  setPluginEnabled,
  setPluginMaster,
  updateTask,
} from '@/lib/api'
import { toastBus } from '@/lib/toast'
import type { DeepSection } from '@/types'
import { deepBool, seedDeepSettings } from '@/lib/deepSettings'
import { ensureGlobalShortcut } from '@/lib/globalShortcut'
import { clampDeepDraft } from './bounds'
import type { useSettingsState } from './useSettingsState'

export function useSettingsLists(state: ReturnType<typeof useSettingsState>) {
  const {
    activeTab,
    deepDraft,
    deepSections,
    isOpen,
    setDeepDraft,
    setDeepSections,
    setPluginView,
    setScheduleJobs,
    setTasks,
    t,
  } = state

  const reloadJobs = useCallback(() => {
    listSchedules()
      .then((r) => setScheduleJobs(r.jobs ?? []))
      .catch(() => {})
  }, [])
  const reloadTasks = useCallback(() => {
    getTasks()
      .then(setTasks)
      .catch(() => {})
  }, [])

  async function handleScheduleCreate(
    task: string,
    cron: string,
    delayMinutes?: number,
    maxRuns?: number,
  ) {
    try {
      await createSchedule(task, cron, delayMinutes, maxRuns)
      reloadJobs()
      toastBus.success(t('chat.schedCreated'))
    } catch {
      toastBus.error(t('chat.schedCreateFailed'))
    }
  }
  async function handleScheduleDelete(id: string) {
    try {
      await deleteSchedule(id)
      reloadJobs()
    } catch {
      toastBus.error(t('chat.schedDeleteFailed'))
    }
  }
  async function handleTaskToggle(task: TaskItem) {
    try {
      await updateTask(task.id, { status: task.status === 'done' ? 'open' : 'done' })
      reloadTasks()
    } catch {
      toastBus.error(t('settings.taskFailed'))
    }
  }
  async function handleTaskDelete(id: string) {
    try {
      await deleteTask(id)
      reloadTasks()
    } catch {
      toastBus.error(t('settings.taskFailed'))
    }
  }
  // I7-3: the list here was read-only and checkable, although POST /api/tasks
  // exists and the agent tab already uses it.
  const [taskDraft, setTaskDraft] = useState('')
  const [taskBusy, setTaskBusy] = useState(false)
  async function handleTaskCreate() {
    const title = taskDraft.trim()
    if (!title) return
    setTaskBusy(true)
    try {
      await createTask(title)
      setTaskDraft('')
      reloadTasks()
    } catch {
      toastBus.error(t('settings.taskFailed'))
    } finally {
      setTaskBusy(false)
    }
  }

  async function syncShortcut(enabled: boolean) {
    const outcome = await ensureGlobalShortcut(enabled)
    if (outcome !== 'failed') return
    // A chord another app owns must not stay written down as on. The shell
    // already released its attempt; the register follows it back to off.
    try {
      await saveSections({ shortcuts: { 'shortcuts.global_enabled': false } })
    } catch {
      // The rejection the user needs to hear is the registration, below.
    }
    setDeepSections(
      (prev) =>
        prev?.map((sec) =>
          sec.key === 'shortcuts'
            ? {
                ...sec,
                fields: sec.fields.map((f) =>
                  f.key === 'shortcuts.global_enabled' ? { ...f, value: false } : f,
                ),
              }
            : sec,
        ) ?? null,
    )
    setDeepDraft((prev) => ({
      ...prev,
      shortcuts: { ...(prev.shortcuts ?? {}), 'shortcuts.global_enabled': false },
    }))
    toastBus.error(t('settings.shortcutFailed'))
  }

  function applyDeepView(sections: DeepSection[] | null) {
    setDeepSections(sections)
    // I3-4: the same state goes into the client pipe — a save in the panel
    // then takes effect without a reload (font size, animations, timestamps).
    seedDeepSettings(sections)
    void syncShortcut(deepBool('shortcuts.global_enabled'))
    if (!sections) return
    setDeepDraft((prev) => {
      const next: Record<string, Record<string, string | number | boolean>> = { ...prev }
      for (const sec of sections) {
        const cur = next[sec.key] ?? {}
        for (const f of sec.fields) cur[f.key] = f.value ?? f.default ?? ''
        next[sec.key] = cur
      }
      return next
    })
  }

  // Both loaders are useCallback — otherwise the effects below hang on a
  // function that is recreated on every render (exhaustive-deps).
  const loadDeepRegister = useCallback(async () => {
    try {
      const st = await getSettings()
      applyDeepView(st.deep ?? null)
    } catch {
      /* backend unreachable — the sections show no register rows */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadPluginStore = useCallback(async () => {
    try {
      const [view, st] = await Promise.all([getPlugins(), getSettings()])
      setPluginView(view)
      applyDeepView(st.deep ?? null)
    } catch {
      /* backend unreachable — the section shows empty lists */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // I3-V5: the register is read everywhere — appearance, engine and the plugin
  // store all show rows of it. So it loads when the panel opens, not per tab.
  useEffect(() => {
    if (!isOpen) return
    void loadDeepRegister()
  }, [isOpen, loadDeepRegister])

  useEffect(() => {
    if (!isOpen || activeTab !== 'plugins') return
    void loadPluginStore()
  }, [isOpen, activeTab, loadPluginStore])

  async function handlePluginToggle(id: string, enabled: boolean) {
    try {
      await setPluginEnabled(id, enabled)
      setPluginView(
        (prev) =>
          prev && {
            ...prev,
            public: prev.public.map((p) => (p.id === id ? { ...p, enabled } : p)),
            personal: prev.personal.map((p) => (p.id === id ? { ...p, enabled } : p)),
          },
      )
    } catch {
      toastBus.error(t('settings.pluginToggleFailed'))
    }
  }
  // E1: master kill switch — off = stock Ephe (every toggle inactive).
  async function handlePluginMasterToggle(enabled: boolean) {
    try {
      const res = await setPluginMaster(enabled)
      setPluginView((prev) => prev && { ...prev, master_enabled: res.master_enabled })
      toastBus.success(
        t(res.master_enabled ? 'settings.pluginsMasterOn' : 'settings.pluginsMasterOff'),
      )
    } catch {
      toastBus.error(t('settings.pluginToggleFailed'))
    }
  }

  function setDeepField(secKey: string, fieldKey: string, value: string | number | boolean) {
    setDeepDraft((prev) => ({ ...prev, [secKey]: { ...(prev[secKey] ?? {}), [fieldKey]: value } }))
  }

  /**
   * I6-1: write the register (settings.json). The only caller is
   * saveSettings — one button serves both storage areas, so nothing reports by
   * itself here any more; the result says whether it worked and what the server
   * said about it. The caller decides what the user hears.
   */
  /** One write for an imported or reset appearance profile; a missing section
   *  refuses the whole write. */
  async function saveAppearanceProfile(
    values: Record<string, string | number | boolean>,
  ): Promise<{ ok: boolean; detail?: string }> {
    if (!deepSections) return { ok: false, detail: 'appearance register missing' }
    const appearance = deepSections.find((section) => section.key === 'appearance')
    if (!appearance) return { ok: false, detail: 'appearance register missing' }
    const current: Record<string, string | number | boolean> = {}
    for (const field of appearance.fields) {
      current[field.key] = field.value ?? field.default ?? ''
    }
    const next = { ...current, ...values }
    try {
      await saveSections({ appearance: next })
      const updated = deepSections.map((section) =>
        section.key === 'appearance'
          ? {
              ...section,
              fields: section.fields.map((field) => {
                const value = next[field.key]
                return value === undefined ? field : { ...field, value }
              }),
            }
          : section,
      )
      setDeepSections(updated)
      setDeepDraft((prev) => ({
        ...prev,
        appearance: { ...(prev.appearance ?? {}), ...next },
      }))
      seedDeepSettings(updated)
      return { ok: true }
    } catch (e) {
      return { ok: false, detail: e instanceof Error && e.message ? e.message : undefined }
    }
  }

  async function saveDeepSettings(scope?: string[]): Promise<{ ok: boolean; detail?: string }> {
    try {
      // I3-3: clamped to the register gate before sending — a value
      // outside it is a typo, not a 422 toast for the user.
      const clamped = clampDeepDraft(deepDraft, deepSections)
      const payload = scope
        ? Object.fromEntries(Object.entries(clamped).filter(([key]) => scope.includes(key)))
        : clamped
      await saveSections(payload)
      if (!scope) {
        // Set fresh instead of leaving the draft: the draft has to follow the
        // server values, or the footer button counter would stay after saving.
        await loadDeepRegister()
      } else {
        // A scoped save is the instant path: refresh only its baseline, so a
        // draft in another section is not silently discarded by a full reload.
        // The global pipe is seeded from the same sections, or the accent, type
        // and reading width would only move after the next full load.
        const updated =
          deepSections?.map((sec) =>
            scope.includes(sec.key)
              ? {
                  ...sec,
                  fields: sec.fields.map((f) => {
                    const value = payload[sec.key]?.[f.key]
                    return value === undefined ? f : { ...f, value }
                  }),
                }
              : sec,
          ) ?? null
        setDeepSections(updated)
        setDeepDraft((prev) => ({ ...prev, ...payload }))
        seedDeepSettings(updated)
      }
      return { ok: true }
    } catch (e) {
      return { ok: false, detail: e instanceof Error && e.message ? e.message : undefined }
    }
  }

  return {
    reloadJobs,
    reloadTasks,
    handleScheduleCreate,
    handleScheduleDelete,
    handleTaskToggle,
    handleTaskDelete,
    handleTaskCreate,
    taskDraft,
    setTaskDraft,
    taskBusy,
    loadPluginStore,
    loadDeepRegister,
    handlePluginMasterToggle,
    handlePluginToggle,
    setDeepField,
    saveDeepSettings,
    saveAppearanceProfile,
  }
}
