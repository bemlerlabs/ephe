/**
 * I7-5: the rows the tab itself does not know — their index.
 *
 * The area search so far only found tab fields (matchFields). Everything with
 * its own endpoint (capabilities, MCP, voices, network) was
 * unfindable even though the surface shows it. This index names those rows by
 * their full i18n key; the search itself stays in settingsSearch.ts.
 *
 * Only rows you can touch or read off — not group headings,
 * those are already reachable through the area name.
 */
import type { TabKey } from '../types'
import { SHORTCUTS } from '@/lib/shortcuts'

export interface RowIndexEntry {
  tab: TabKey
  /** Full i18n key, because two areas do not live under `settings`. */
  key: string
}

export const ROW_INDEX: readonly RowIndexEntry[] = [
  // Appearance
  { tab: 'appearance', key: 'settings.appearanceTitle' },
  { tab: 'appearance', key: 'settings.appearanceProfileExport' },
  { tab: 'appearance', key: 'settings.appearanceProfileImport' },
  { tab: 'appearance', key: 'settings.appearanceProfileReset' },
  // Engine (including the image endpoint)
  { tab: 'engine', key: 'settings.engineNotConfigured' },
  { tab: 'engine', key: 'settings.endpointLabel' },
  { tab: 'engine', key: 'settings.apiKeyLabel' },
  { tab: 'behaviour', key: 'settings.workspaceTitle' },
  { tab: 'engine', key: 'settings.outputDirTitle' },
  { tab: 'engine', key: 'environment.title' },
  { tab: 'engine', key: 'settings.imageBaseUrl' },
  { tab: 'engine', key: 'settings.imageModel' },
  { tab: 'engine', key: 'settings.imageApiKey' },
  { tab: 'engine', key: 'settings.imageTest' },
  // Generation
  { tab: 'generation', key: 'settings.genTemperature' },
  { tab: 'generation', key: 'settings.genTopP' },
  { tab: 'generation', key: 'settings.genMaxTokens' },
  { tab: 'generation', key: 'settings.genToolBudget' },
  { tab: 'generation', key: 'settings.genContextWindow' },
  { tab: 'generation', key: 'settings.genMemoryMax' },
  // Wave 2/B4: the engine's reasoning-effort option.
  { tab: 'generation', key: 'settings.genReasoning' },
  // Audio
  { tab: 'voice', key: 'settings.audioEngineRow' },
  { tab: 'voice', key: 'settings.piperVoice' },
  { tab: 'voice', key: 'settings.audioInstalledVoices' },
  { tab: 'voice', key: 'settings.edgeVoice' },
  { tab: 'voice', key: 'settings.autoSpeak' },
  { tab: 'voice', key: 'settings.voiceTest' },
  { tab: 'voice', key: 'settings.sttModel' },
  { tab: 'voice', key: 'settings.sttLanguage' },
  // Mobile
  { tab: 'mobile', key: 'settings.telegramTitle' },
  { tab: 'mobile', key: 'settings.telegramDevicesTitle' },
  { tab: 'mobile', key: 'settings.discordTitle' },
  // Language
  { tab: 'language', key: 'settings.languageRow' },
  // Behaviour — the approval register moved here from Privacy (Wave 4.3).
  { tab: 'behaviour', key: 'settings.privacyProfileRow' },
  { tab: 'behaviour', key: 'settings.sandboxTitle' },
  // Wave 2/B3: the two categories that may be made to ask more often.
  { tab: 'behaviour', key: 'settings.askMoreSafe' },
  { tab: 'behaviour', key: 'settings.askMoreNetwork' },
  // Privacy — the store rows that stay in this area.
  { tab: 'privacy', key: 'settings.clearLocalData' },
  // Wave 4: the store row beside the browser-cache row — the one that deletes
  // files on the server's machine, not in the browser.
  { tab: 'privacy', key: 'settings.sessionStoreRow' },
  { tab: 'privacy', key: 'settings.clearAllChats' },
  // Knowledge
  { tab: 'memory', key: 'settings.memoryVectors' },
  { tab: 'memory', key: 'settings.memoryProvider' },
  { tab: 'memory', key: 'settings.memoryScope' },
  { tab: 'memory', key: 'settings.memoryExport' },
  { tab: 'memory', key: 'settings.memoryImport' },
  // W3-51: the row that opens the holdings page was the one memory row without
  // an index entry — rendered, never findable.
  { tab: 'memory', key: 'settings.memoryOpenPage' },
  { tab: 'memory', key: 'settings.clearMemory' },
  // Persona
  { tab: 'persona', key: 'settings.personaSource' },
  // Skills
  { tab: 'skills', key: 'settings.skillsGroupInstall' },
  { tab: 'skills', key: 'settings.skillsGroupMine' },
  // MCP
  { tab: 'mcp', key: 'settings.mcpServers' },
  { tab: 'mcp', key: 'settings.mcpTools' },
  { tab: 'mcp', key: 'settings.mcpCatalog' },
  // Plugin Store
  { tab: 'plugins', key: 'settings.pluginsMaster' },
  { tab: 'plugins', key: 'settings.plugins.public' },
  { tab: 'plugins', key: 'settings.plugins.personal' },
  { tab: 'plugins', key: 'settings.plugins.orphans' },
  // Hooks
  { tab: 'hooks', key: 'settings.hooksEvent.pre_tool' },
  { tab: 'hooks', key: 'settings.hooksEvent.post_tool' },
  { tab: 'hooks', key: 'settings.hooksEvent.session_start' },
  { tab: 'hooks', key: 'settings.hooksEvent.turn_end' },
  { tab: 'hooks', key: 'settings.hooksEvent.pre_compact' },
  { tab: 'hooks', key: 'settings.hooksGroupRecent' },
  // Code execution
  { tab: 'code-exec', key: 'settings.codeExecIntegrityTitle' },
  { tab: 'code-exec', key: 'settings.codeExecGuest' },
  { tab: 'code-exec', key: 'settings.codeExecCellLicense' },
  { tab: 'code-exec', key: 'settings.codeExecNetwork' },
  { tab: 'code-exec', key: 'settings.codeExecPreopens' },
  { tab: 'code-exec', key: 'settings.codeExecFuel' },
  { tab: 'code-exec', key: 'settings.codeExecMemory' },
  { tab: 'code-exec', key: 'settings.codeExecTimeout' },
  { tab: 'code-exec', key: 'settings.codeExecDisk' },
  { tab: 'code-exec', key: 'settings.codeExecWorkQuota' },
  { tab: 'code-exec', key: 'settings.codeExecOutput' },
  { tab: 'code-exec', key: 'settings.codeExecJournal' },
  // Schedule
  { tab: 'cron', key: 'scheduler.taskLabel' },
  { tab: 'cron', key: 'scheduler.cronLabel' },
  { tab: 'cron', key: 'scheduler.delayLabel' },
  { tab: 'cron', key: 'scheduler.maxRunsLabel' },
  { tab: 'cron', key: 'scheduler.history' },
  { tab: 'cron', key: 'automation.templates' },
  { tab: 'cron', key: 'automation.keepAwake' },
  // Network
  { tab: 'network', key: 'settings.networkBind' },
  { tab: 'network', key: 'settings.networkReach' },
  { tab: 'network', key: 'settings.networkToken' },
  { tab: 'network', key: 'settings.networkSetupTitle' },
  { tab: 'network', key: 'settings.networkRoots' },
  { tab: 'network', key: 'settings.networkProxy' },
  { tab: 'network', key: 'settings.networkPrivate' },
  // Shortcuts — read off the one table: a row is named by its description, and a
  // list copied by hand is how a 12-entry index survives a 13-entry table.
  ...SHORTCUTS.map((s) => ({ tab: 'shortcuts' as TabKey, key: s.labelKey })),
  { tab: 'shortcuts', key: 'settings.globalShortcutLabel' },
  // About Ephe
  { tab: 'about', key: 'settings.aboutVersion' },
  { tab: 'about', key: 'settings.aboutLicense' },
  { tab: 'about', key: 'settings.aboutProvider' },
  { tab: 'about', key: 'settings.aboutModel' },
  { tab: 'about', key: 'settings.aboutOffline' },
]
