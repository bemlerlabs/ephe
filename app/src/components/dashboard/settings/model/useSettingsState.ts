'use client'

import * as React from 'react'
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatStore } from '@/store/chatStore'
import { AppSettings, healthCheck } from '@/lib/api'
import type {
  PluginView,
  DeepSection,
  ModelOption,
  MobileQR,
  ScheduleJob,
  TaskItem,
  SkillSummary,
  ImageSettings,
  ImageEndpointProbe,
  VoiceSettings,
  SecuritySettings,
  MemoryEntry,
  SkillPackInfo,
  McpHealthServer,
  McpCatalogEntry,
  CodeExecPolicy,
  HooksView,
  NetworkStatus,
} from '@/lib/api'
import type { SettingsPanelProps, TabKey } from '../types'

// One definition of "a tab stop in the dialog". Initial focus and the trap used
// to carry separate strings: the initial one also matched disabled buttons, so a
// disabled first control would have left the focus on <body> instead of the panel.
const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function useSettingsState(props: SettingsPanelProps) {
  const { isOpen, onClose, initialTab } = props
  const { t, i18n } = useTranslation()
  const currentSession = useChatStore((s) => s.currentSession)

  const [activeTab, setActiveTab] = useState<TabKey>('engine')
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Custom model settings (visible when custom selected)
  const [customEndpoint, setCustomEndpoint] = useState('')
  const [customApiKey, setCustomApiKey] = useState('')
  // F: the workspace/project folder (the shell-/file tools work inside it)
  const [workspaceDraft, setWorkspaceDraft] = useState('')
  const [wsPickerOpen, setWsPickerOpen] = useState(false)
  // R44 (P4): output path for the document/image tools (overrides the Downloads default)
  const [outputDraft, setOutputDraft] = useState('')
  // Wave 5: draft of the deep generation parameters (the fine-tuning levers).
  // null = "not set" (the server default applies); an empty input string = unset.
  const [genDraft, setGenDraft] = useState<Record<string, string>>({})
  // Wave 6: plugin-store view + the deep section register
  const [pluginView, setPluginView] = useState<PluginView | null>(null)
  // S-wave: client-side plugin filter (the app-shell search field)
  const [pluginQuery, setPluginQuery] = useState('')
  // E4b: expanded detail sheet (plugin id or null)
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null)
  const [deepSections, setDeepSections] = useState<DeepSection[] | null>(null)
  // I3-V5: the search sits in the navigation (as in the reference) — it finds
  // areas AND single settings and jumps to them.
  const [settingsQuery, setSettingsQuery] = useState('')
  const [deepDraft, setDeepDraft] = useState<
    Record<string, Record<string, string | number | boolean>>
  >({})

  // G5: live model list from the engine (instead of hard-coded)
  const [liveModels, setLiveModels] = useState<ModelOption[]>([])
  const [memoryTotal, setMemoryTotal] = useState<number | null>(null)
  const [confirmClearMemory, setConfirmClearMemory] = useState(false)

  // P4: auto read-aloud (localStorage — a pure frontend preference, no backend field)
  const [autoSpeak, setAutoSpeak] = useState(() => localStorage.getItem('ephe.autospeak') === '1')
  const [confirmClearLocal, setConfirmClearLocal] = useState(false)

  // P5-Hub: skills / cron / tasks / about
  const [skills, setSkills] = useState<SkillSummary[] | null>(null)
  const [scheduleJobs, setScheduleJobs] = useState<ScheduleJob[]>([])
  const [tasks, setTasks] = useState<TaskItem[] | null>(null)
  const [about, setAbout] = useState<Awaited<ReturnType<typeof healthCheck>> | null>(null)
  // W18/A5: what the running backend last said about its own engine — the state
  // (ok | busy | unreachable) and whether the engine refused this start's credential.
  // Visible in the panel — not just as a fleeting toast.
  const [engineHealth, setEngineHealth] = useState<Awaited<ReturnType<typeof healthCheck>> | null>(
    null,
  )
  const [engineTesting, setEngineTesting] = useState(false)
  // R28: persona editor state (loaded on first activation of the persona tab)
  const [personaText, setPersonaText] = useState('')
  const [personaSource, setPersonaSource] = useState('')
  const [personaLoading, setPersonaLoading] = useState(false)
  const [personaSaving, setPersonaSaving] = useState(false)

  // W44 P1c: MCP server attachment (GET/PUT /settings/mcp)
  const [mcpServers, setMcpServers] = useState<string[]>([])
  const [mcpSource, setMcpSource] = useState<string>('')
  const [mcpTools, setMcpTools] = useState<string[]>([])
  const [mcpLoading, setMcpLoading] = useState(false)
  const [mcpSaving, setMcpSaving] = useState(false)
  // E3c: health probe (spec → status) + the curated catalogue
  const [mcpHealth, setMcpHealth] = useState<Record<string, McpHealthServer>>({})
  const [mcpHealthLoading, setMcpHealthLoading] = useState(false)
  const [mcpCatalog, setMcpCatalog] = useState<McpCatalogEntry[] | null>(null)
  // P6 B7 (ref-01 norm): the catalogue is searchable (name/description/category).
  const [mcpCatalogQuery, setMcpCatalogQuery] = useState('')

  const [skillsBusy, setSkillsBusy] = useState(false)
  const [skillsMsg, setSkillsMsg] = useState<string | null>(null)
  const [skillUrl, setSkillUrl] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [imageCfg, setImageCfg] = useState<ImageSettings | null>(null)
  const [imageDraft, setImageDraft] = useState({ base_url: '', model: '', api_key: '' })
  const [imageBusy, setImageBusy] = useState(false)
  const [imageProbe, setImageProbe] = useState<ImageEndpointProbe | null>(null)
  // R18: voice settings (voice.json) instead of only the localStorage voice
  const [voiceCfg, setVoiceCfg] = useState<VoiceSettings | null>(null)
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null)
  // R16: curated topic packs (offline index)
  const [packIndex, setPackIndex] = useState<SkillPackInfo[] | null>(null)
  // R23: security settings (approval profile + shell sandbox)
  const [securityCfg, setSecurityCfg] = useState<SecuritySettings | null>(null)
  // I6-4: the read side of the user hooks (GET /api/settings/hooks)
  const [hooksView, setHooksView] = useState<HooksView | null>(null)
  const [hooksLoading, setHooksLoading] = useState(false)
  // I6-6: the network's actual state (GET /api/network/status)
  const [networkStatus, setNetworkStatus] = useState<NetworkStatus | null>(null)
  // Wave E1: the effective caps on code execution (read-only, one policy truth)
  const [codeExecCfg, setCodeExecCfg] = useState<CodeExecPolicy | null>(null)
  // R19: memory management (browse/search/delete/export/import)
  const [memEntries, setMemEntries] = useState<MemoryEntry[] | null>(null)
  const [memQuery, setMemQuery] = useState('')
  // R40: the workspace collection that speaks here — without it there is no way
  // to see which folder counts at all (editing lives in the knowledge tab).
  const [memoryScope, setMemoryScope] = useState<string | null>(null)
  const [memoryProvider, setMemoryProvider] = useState<string | null>(null)

  const [mobileQR, setMobileQR] = useState<MobileQR | null>(null)
  const [mobileLoading, setMobileLoading] = useState(false)
  const [mobileError, setMobileError] = useState<string | null>(null)
  const [mobileConnected, setMobileConnected] = useState(false)

  // R20 F-12: dialog a11y — initial focus + focus trap, and the Escape close.
  // The close used to sit in a second effect with its own window listener, so a
  // single Escape ran onClose twice.
  const panelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  const trapPanelFocus = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return
    const focusables = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)
    if (focusables.length === 0) return
    const first = focusables[0]!
    const last = focusables[focusables.length - 1]!
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  // R28: deep-link support — /personality dispatches this to preselect the tab.
  //
  // W10 (FINDINGS 2026-10-12, medium): the command palette sends `ephe:open-settings`
  // and `ephe:settings-tab` in ONE handler, and the panel's open-effect
  // (useSettingsCore) then lands on `initialTab ?? 'engine'` — so every palette entry
  // opened Engine whatever it said, while a sidebar row (which goes through the
  // `initialTab` prop) landed right. A named request therefore becomes the effective
  // initial tab of the open it arrives with; the tab the user asked for is the tab
  // that opens. A control-level request (the palette's row entries) carries the row's
  // own label as the panel's search, so the panel names the row it lands on.
  const [requestedTab, setRequestedTab] = useState<TabKey | null>(null)
  const initialTabResolved = requestedTab ?? initialTab
  useEffect(() => {
    const onTab = (e: Event) => {
      const detail = (e as CustomEvent<{ tab?: string; query?: string }>).detail
      if (!detail) return
      if (detail.tab) {
        // Both, on purpose: the resolved initial tab makes the open-effect land here,
        // and the direct write switches an already-open panel in the same tick.
        setRequestedTab(detail.tab as TabKey)
        setActiveTab(detail.tab as TabKey)
      }
      if (detail.query) setSettingsQuery(detail.query)
    }
    window.addEventListener('ephe:settings-tab', onTab)
    return () => window.removeEventListener('ephe:settings-tab', onTab)
  }, [])

  // A request holds for the open it arrived with. A closed panel keeps neither it nor
  // the search it came with, so the next open starts from the prop again (sidebar
  // 'plugins' → marketplace) and shows the navigation instead of a stale filter.
  useEffect(() => {
    if (isOpen) return
    setRequestedTab(null)
    setSettingsQuery('')
  }, [isOpen])

  return {
    isOpen,
    onClose,
    // The resolved tab, not the raw prop: the open-effect reads this value.
    initialTab: initialTabResolved,
    t,
    i18n,
    currentSession,
    activeTab,
    setActiveTab,
    settings,
    setSettings,
    loading,
    setLoading,
    saving,
    setSaving,
    saved,
    setSaved,
    customEndpoint,
    setCustomEndpoint,
    customApiKey,
    setCustomApiKey,
    workspaceDraft,
    setWorkspaceDraft,
    wsPickerOpen,
    setWsPickerOpen,
    outputDraft,
    setOutputDraft,
    genDraft,
    setGenDraft,
    pluginView,
    setPluginView,
    pluginQuery,
    setPluginQuery,
    expandedPlugin,
    setExpandedPlugin,
    settingsQuery,
    setSettingsQuery,
    deepDraft,
    setDeepDraft,
    deepSections,
    setDeepSections,
    liveModels,
    setLiveModels,
    memoryTotal,
    memoryScope,
    setMemoryScope,
    memoryProvider,
    setMemoryProvider,
    setMemoryTotal,
    confirmClearMemory,
    setConfirmClearMemory,
    autoSpeak,
    setAutoSpeak,
    confirmClearLocal,
    setConfirmClearLocal,
    skills,
    setSkills,
    scheduleJobs,
    setScheduleJobs,
    tasks,
    setTasks,
    about,
    setAbout,
    engineHealth,
    setEngineHealth,
    engineTesting,
    setEngineTesting,
    personaText,
    setPersonaText,
    personaSource,
    setPersonaSource,
    personaLoading,
    setPersonaLoading,
    personaSaving,
    setPersonaSaving,
    mcpServers,
    setMcpServers,
    mcpSource,
    setMcpSource,
    mcpTools,
    setMcpTools,
    mcpLoading,
    setMcpLoading,
    mcpSaving,
    setMcpSaving,
    mcpHealth,
    setMcpHealth,
    mcpHealthLoading,
    setMcpHealthLoading,
    mcpCatalog,
    setMcpCatalog,
    mcpCatalogQuery,
    setMcpCatalogQuery,
    skillsBusy,
    setSkillsBusy,
    skillsMsg,
    setSkillsMsg,
    skillUrl,
    setSkillUrl,
    fileInputRef,
    imageCfg,
    setImageCfg,
    imageDraft,
    setImageDraft,
    imageBusy,
    setImageBusy,
    imageProbe,
    setImageProbe,
    voiceCfg,
    setVoiceCfg,
    voiceMsg,
    setVoiceMsg,
    packIndex,
    setPackIndex,
    securityCfg,
    setSecurityCfg,
    hooksView,
    setHooksView,
    hooksLoading,
    setHooksLoading,
    networkStatus,
    setNetworkStatus,
    codeExecCfg,
    setCodeExecCfg,
    memEntries,
    setMemEntries,
    memQuery,
    setMemQuery,
    mobileQR,
    setMobileQR,
    mobileLoading,
    setMobileLoading,
    mobileError,
    setMobileError,
    mobileConnected,
    setMobileConnected,
    panelRef,
    trapPanelFocus,
  }
}
