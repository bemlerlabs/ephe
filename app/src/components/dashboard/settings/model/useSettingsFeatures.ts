'use client'

import { useEffect } from 'react'
import {
  McpHealthServer,
  SecuritySettings,
  VoiceSettings,
  deleteSkill,
  disableSkill,
  enableSkill,
  getImageSettings,
  getCodeExecPolicy,
  getMemoryStats,
  getMobileQR,
  getMobileStatus,
  getPersona,
  getSecuritySettings,
  getVoiceSettings,
  installSkill,
  installSkillFromUrl,
  listMemory,
  listSkills,
  probeMcpHealth,
  saveImageSettings,
  saveSecuritySettings,
  saveVoiceSettings,
  searchMemory,
  synthesizeSpeech,
  testImageEndpoint,
  updatePersona,
} from '@/lib/api'
import { toastBus } from '@/lib/toast'
import type { useSettingsState } from './useSettingsState'

export function useSettingsFeatures(state: ReturnType<typeof useSettingsState>) {
  const {
    activeTab,
    imageCfg,
    imageDraft,
    isOpen,
    memQuery,
    personaSource,
    personaText,
    securityCfg,
    codeExecCfg,
    setCodeExecCfg,
    setImageBusy,
    setImageCfg,
    setImageDraft,
    setImageProbe,
    setMcpHealth,
    setMcpHealthLoading,
    setMemEntries,
    setMemoryScope,
    setMemoryProvider,
    setMemoryTotal,
    setMobileConnected,
    setMobileError,
    setMobileLoading,
    setMobileQR,
    setPersonaLoading,
    setPersonaSaving,
    setPersonaSource,
    setPersonaText,
    setSecurityCfg,
    setSkills,
    setSkillsBusy,
    setSkillsMsg,
    setVoiceCfg,
    setVoiceMsg,
    skillUrl,
    t,
    voiceCfg,
  } = state

  function handleMcpHealthCheck() {
    setMcpHealthLoading(true)
    probeMcpHealth()
      .then((r) => {
        const next: Record<string, McpHealthServer> = {}
        for (const s of r.servers ?? []) next[s.spec] = s
        setMcpHealth(next)
      })
      .catch(() => toastBus.error(t('common.changeFailed')))
      .finally(() => setMcpHealthLoading(false))
  }

  function reloadSkills() {
    listSkills()
      .then((r) => setSkills(r.skills))
      .catch(() => setSkills([]))
  }

  async function handleSkillInstall(file: File) {
    setSkillsBusy(true)
    setSkillsMsg(null)
    try {
      const r = await installSkill(file)
      const done = r.installed.length + r.updated.length
      setSkillsMsg(
        done > 0 ? t('settings.skillsInstallDone', { done }) : t('settings.skillsInstallNothing'),
      )
      reloadSkills()
    } catch (e) {
      setSkillsMsg(e instanceof Error ? e.message : 'Install failed')
    } finally {
      setSkillsBusy(false)
    }
  }

  async function handleSkillInstallUrl() {
    const url = skillUrl.trim()
    if (!url) return
    setSkillsBusy(true)
    setSkillsMsg(null)
    try {
      const r = await installSkillFromUrl(url)
      const done = r.installed.length + r.updated.length
      setSkillsMsg(
        done > 0 ? t('settings.skillsInstallDone', { done }) : t('settings.skillsInstallNothing'),
      )
      reloadSkills()
    } catch (e) {
      setSkillsMsg(e instanceof Error ? e.message : 'Install failed')
    } finally {
      setSkillsBusy(false)
    }
  }

  async function handleSkillToggle(name: string, disabled: boolean) {
    try {
      await (disabled ? enableSkill(name) : disableSkill(name))
      reloadSkills()
    } catch {
      // F-11: no route-side toast — surface the failure here.
      toastBus.error(t('common.changeFailed'))
    }
  }

  async function handleSkillDelete(name: string) {
    try {
      await deleteSkill(name)
      reloadSkills()
    } catch {
      // F-12: builtin refusals must be visible, not swallowed.
      toastBus.error(t('common.changeFailed'))
    }
  }

  function loadImageSettings() {
    getImageSettings()
      .then((cfg) => {
        setImageCfg(cfg)
        setImageDraft({ base_url: cfg.base_url, model: cfg.model, api_key: '' })
      })
      .catch(() => setImageCfg(null))
  }

  async function handleImageSave() {
    setImageBusy(true)
    try {
      // Send api_key only when it was typed — otherwise the stored key remains.
      const payload: { base_url: string; model: string; api_key?: string } = { ...imageDraft }
      if (!imageDraft.api_key) delete payload.api_key
      const cfg = await saveImageSettings(payload)
      setImageCfg(cfg)
      setImageDraft({ base_url: cfg.base_url, model: cfg.model, api_key: '' })
    } catch {
      // F-13: try/finally alone turned API errors into unhandled rejections.
      toastBus.error(t('common.changeFailed'))
    } finally {
      setImageBusy(false)
    }
  }

  async function handleImageTest() {
    setImageBusy(true)
    setImageProbe(null)
    try {
      setImageProbe(await testImageEndpoint())
    } catch (e) {
      setImageProbe({
        reachable: false,
        models: [],
        base_url_used: '',
        detail: e instanceof Error ? e.message : 'Probe failed',
      })
    } finally {
      setImageBusy(false)
    }
  }

  useEffect(() => {
    if (isOpen && activeTab === 'engine' && imageCfg === null) loadImageSettings()
    // loadImageSettings is stable enough (setState-only); imageCfg gates the effect.
  }, [isOpen, activeTab, imageCfg])

  // R19: load the memory entries (diversified search over Chroma similarity).
  // R40: a search hit carries its real Chroma document id into the UI — only that
  // one is valid against DELETE /api/memory/{id}. Earlier stand-ins (score/index)
  // turned every delete from the search into a 404.
  useEffect(() => {
    if (!isOpen || activeTab !== 'memory') return
    const timer = setTimeout(() => {
      const load = memQuery.trim()
        ? searchMemory(memQuery.trim(), 20).then((r) =>
            r.results.map((h) => ({ id: h.id, text: h.text, metadata: h.metadata })),
          )
        : listMemory(50).then((r) => r.entries)
      load.then((entries) => setMemEntries(entries)).catch(() => setMemEntries([]))
    }, 250)
    return () => clearTimeout(timer)
  }, [isOpen, activeTab, memQuery])

  function reloadMemory() {
    if (memQuery.trim()) {
      searchMemory(memQuery.trim(), 20)
        .then((r) =>
          setMemEntries(r.results.map((h) => ({ id: h.id, text: h.text, metadata: h.metadata }))),
        )
        .catch(() => setMemEntries([]))
    } else {
      listMemory(50)
        .then((r) => setMemEntries(r.entries))
        .catch(() => setMemEntries([]))
    }
    getMemoryStats()
      .then((s) => {
        setMemoryTotal(s.total)
        setMemoryScope(s.scope ?? null)
        setMemoryProvider(s.provider ?? null)
      })
      .catch(() => setMemoryTotal(null))
  }

  useEffect(() => {
    if (isOpen && activeTab === 'voice' && voiceCfg === null) {
      getVoiceSettings()
        .then(setVoiceCfg)
        .catch(() => setVoiceCfg(null))
    }
  }, [isOpen, activeTab, voiceCfg])

  useEffect(() => {
    if (isOpen && activeTab === 'privacy' && securityCfg === null) {
      getSecuritySettings()
        .then(setSecurityCfg)
        .catch(() => setSecurityCfg(null))
    }
    // Wave E1 / I6-5: the cell caps belong in their own section — the card shows
    // the truth about code execution, not a claim about it.
    if (isOpen && activeTab === 'code-exec' && codeExecCfg === null) {
      getCodeExecPolicy()
        .then(setCodeExecCfg)
        .catch(() => setCodeExecCfg(null))
    }
  }, [isOpen, activeTab, securityCfg, codeExecCfg])

  async function handleSecuritySave(patch: Partial<SecuritySettings>) {
    try {
      setSecurityCfg(await saveSecuritySettings(patch))
    } catch {
      // F-14: a silently reverting toggle is a lie — surface the failure.
      toastBus.error(t('common.changeFailed'))
    }
  }

  async function handleVoiceSave(patch: Partial<VoiceSettings>) {
    try {
      const cfg = await saveVoiceSettings(patch)
      setVoiceCfg(cfg)
      setVoiceMsg(null)
    } catch (e) {
      setVoiceMsg(e instanceof Error ? e.message : 'Save failed')
    }
  }

  async function loadMobileQR() {
    setMobileLoading(true)
    setMobileError(null)
    setMobileConnected(false)
    try {
      setMobileQR(await getMobileQR('auto'))
    } catch (e) {
      setMobileQR(null)
      setMobileError(e instanceof Error ? e.message : 'QR konnte nicht geladen werden')
    } finally {
      setMobileLoading(false)
    }
  }

  useEffect(() => {
    if (!isOpen || activeTab !== 'mobile') return
    void loadMobileQR()
  }, [isOpen, activeTab])

  useEffect(() => {
    if (!isOpen || activeTab !== 'mobile') return
    setMobileConnected(false)
    const id = setInterval(async () => {
      try {
        const s = await getMobileStatus()
        setMobileConnected(s.connected)
      } catch {
        /* Backend offline for a moment — ignore, the next tick retries */
      }
    }, 2000)
    return () => clearInterval(id)
  }, [isOpen, activeTab])

  async function testVoice() {
    try {
      const url = await synthesizeSpeech('Ephe — Testsprecher.')
      await new Audio(url).play()
    } catch {
      toastBus.error(t('settings.voiceTestFailed'))
    }
  }

  // R28: load the persona on first activation of its tab (lazy, like memory)
  useEffect(() => {
    if (activeTab !== 'persona' || personaSource) return
    setPersonaLoading(true)
    getPersona()
      .then((res) => {
        setPersonaText(res.text)
        setPersonaSource(res.source)
      })
      .catch(() => toastBus.error(t('settings.personaLoadFailed')))
      .finally(() => setPersonaLoading(false))
  }, [activeTab, personaSource, t])

  const savePersona = () => {
    setPersonaSaving(true)
    updatePersona(personaText)
      .then((res) => {
        setPersonaText(res.text)
        setPersonaSource(res.source)
        toastBus.success(t('settings.personaSaved'))
      })
      .catch((err: Error) => toastBus.error(err?.message || t('settings.personaSaveFailed')))
      .finally(() => setPersonaSaving(false))
  }

  return {
    handleMcpHealthCheck,
    reloadSkills,
    handleSkillInstall,
    handleSkillInstallUrl,
    handleSkillToggle,
    handleSkillDelete,
    loadImageSettings,
    handleImageSave,
    handleImageTest,
    reloadMemory,
    handleSecuritySave,
    handleVoiceSave,
    loadMobileQR,
    testVoice,
    savePersona,
  }
}
