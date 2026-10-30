/**
 * W3-88 — the German surface carries no English.
 *
 * `de.json` is the product's own German surface: a user who switches the UI to
 * German has to read German, end to end (AGENTS.md, "Language"). The defect this
 * gate names is the paste — a leaf copied from `en.json` and left in English
 * because it looked short or technical enough to skip. Every neighbouring gate
 * passes over it: key parity (`completeness.test.ts`), weight (`bundleSize`),
 * terminology (`oneNamePerThing.test.ts`). It is also the first thing the user
 * sees.
 *
 * German shares a set of English forms on purpose — loanwords, brand names,
 * acronyms, model ids, placeholders — so "de === en" cannot fail by itself. An
 * *unexplained* leaf can: every leaf that is byte-identical to its English
 * neighbour has to be named in SAME_BY_DESIGN. The list is checked against the
 * files, so it cannot rot into a blanket exemption (an entry that no longer
 * exists, or that was translated since, fails below).
 *
 * The second class is the half-translated sentence: an English phrase pasted
 * among German ones. A German string does not carry English function words
 * ("with", "your", "from"), so their presence in a de leaf is the tell — checked
 * over the whole file, placeholders and URLs stripped first.
 */
import { describe, it, expect } from 'vitest'
import { deLeaves, enLeaves } from './localesScan'

const en = new Map(enLeaves)

/** Keys whose de leaf reads exactly like its en leaf, and why that is not a leak. */
const SAME_BY_DESIGN = new Set<string>([
  // The Discover shelf keeps the loanword the settings already use, and a unit.
  'discover.tabSkill',
  'discover.kindSkill',
  'discover.did', // {{name}}: {{what}} — the shape carries, not the word
  'discover.cardLatency',
  // Brand and product names.
  'nav.appName', // Ephe
  'welcome.heroTitle', // Ephe Agent
  'update.availableBody', // Ephe {{from}} → {{to}}
  'chat.badgeRemoteOllama', // Remote · Ollama
  'setup.detectEngineLocal', // Ollama
  'settings.discordTitle', // Discord
  'settings.telegramTitle', // Telegram
  // Acronyms and initialisms.
  'update.detailsCommit', // Commit — the German word is the English one
  'settings.aboutUpdates', // Version & Updates — the German heading reads the same
  'settings.api', // API
  'settings.mcp', // MCP
  'artifacts.kind.pdf', // PDF
  'settings.genTopP', // Top-P
  // Model ids and placeholders — not prose.
  'settings.modelOptions.0.label', // gemma4:e4b
  'settings.modelOptions.1.label', // LLaMA 3.1 8B
  'settings.modelOptions.2.label', // Mistral 7B
  'settings.modelOptions.3.label', // Custom Ollama
  'settings.discordTokenPlaceholder', // 143289….abc….ABC
  'settings.telegramTokenPlaceholder', // 123456789:AA…
  'settings.skillsInstallUrlPlaceholder', // https://… (zip/tgz)
  'workbench.steps', // {{done}}/{{total}}
  // Loanwords German uses unchanged (Duden-accepted or product-register terms).
  'a11y.sidebar', // Sidebar
  'agentPanel.auditKindShell', // Shell
  'agentPanel.browserTitle', // Browser
  'agentPanel.gitCommitBtn', // Commit
  'agentPanel.gitCommitted', // Commit {{hash}}
  'agentPanel.memoryTypeProcedural', // Routine
  'agentPanel.replayPause', // Pause
  'agentPanel.reviewStaged', // Staged
  'agentPanel.subagentPrompt', // Prompt:
  'agentPanel.tabBrowser', // Browser
  'agentPanel.tabPreview', // Browser
  'agentPanel.tabTerminal', // Terminal
  'agentPanel.tabTipBrowser.title', // Browser
  'agentPanel.tabTipPreview.title', // Browser
  'agentPanel.tabTipTerminal.title', // Terminal
  'agentPanel.tabTipTrajectory.title', // Replay
  'agentPanel.tabTrajectory', // Replay
  'agentPanel.terminalLive', // Live
  'agentPanel.trajectoryTurn', // Turn
  'agentPanel.workspace', // Workspace
  'artifacts.kind.deck', // Deck — the product's own term for a presentation
  'artifacts.kind.screenshot', // Screenshot
  'chat.engineOffline', // Engine offline
  'chat.offlineCapableRemote', // Remote
  'chat.perm.autonomous', // Auto
  'chat.planTitle', // Plan
  'chat.replayTitle', // Replay
  'chat.skillsTitle', // Skills
  'commandPalette.items.preview', // Browser
  'header.branches', // Branches
  'memory.storeIndex', // Index
  'modelPicker.free', // Free — the plan name the service itself prints
  'modelPicker.sortName', // Name — the same word in both languages
  'modelPicker.tools', // Tools — the German surface's own word for the tool list
  'modelPicker.vision', // Vision — the same term the capability rows already use
  'settings.aboutProvider', // Provider
  'settings.presetDensityStandard', // Standard
  'settings.presetReadingStandard', // Standard
  'settings.presetLayout', // Layout
  'settings.presetLayoutStandard', // Standard
  'settings.aboutVersion', // Version
  'settings.audioTitle', // Audio
  'settings.codeExecGuest', // Interpreter
  'settings.deepSection.chat', // Chat
  'settings.deepSection.hooks', // Hooks
  'settings.deepSection.plugins', // Plugins
  'settings.agentName', // Name — the same word in both languages
  'settings.marketDetail', // Details
  'settings.marketQualityPlugin', // Plugin — the product's own label, the same word in German
  'settings.marketQualityCapabilityPreset', // Capability Preset — product term, same form in both surfaces
  'settings.marketVersion', // Version
  'settings.marketTrustCommunity', // Community
  'settings.agentOriginEphe', // Ephe
  'settings.agentOriginPlugin', // Plugin
  'settings.teamBudget', // Budget
  'settings.engine', // Engine
  'settings.engineOffline', // Engine offline
  'settings.engineTitle', // Engine
  'settings.engine_auto', // Auto
  'settings.hooks', // Hooks
  'settings.hooksTitle', // Hooks
  'settings.networkBind', // Bind
  'settings.persona', // Persona
  'settings.shortcutsGroup.navigation', // Navigation
  'settings.skills', // Skills
  'settings.skillsTitle', // Skills
  'tour.activate.skills', // Skills
  'settings.status', // Status
  'settings.voice', // Audio
  'sidebar.filterTitle', // Filter
  'sidebar.navScheduled', // Automations — the file's own short form ("Automations-Vorlagen")
  'streamGroup.terminal', // Terminal
  'streamGroup.web', // Web
  'update.title', // Updates
  'update.details', // Details
  'update.detailsVersion', // Version
  'update.detailsSize', // Download
  'workspaceBar.neutralWorkspace', // Workspace
  'workspacePicker.quickDesktop', // Desktop
])

/** Leaves the two bundles carry, read the same, and none of which names a reason. */
export function unexplained(
  pairs: Array<[string, string]>,
  english: Map<string, string>,
  allow: Set<string>,
): Array<[string, string]> {
  return pairs.filter(([key, value]) => english.get(key) === value && !allow.has(key))
}

const de = new Map(deLeaves)

/** de leaves pasted from en and not explained by the design list. */
const leaked = unexplained(deLeaves, en, SAME_BY_DESIGN).map(
  ([key, value]) => `${key}: ${JSON.stringify(value)}`,
)

/** Design-list entries that no longer describe the tree: absent, or translated since. */
const stale = [...SAME_BY_DESIGN].filter(
  (key) => de.get(key) === undefined || en.get(key) !== de.get(key),
)

/* ------------------------------------------------------------------ */
/* Class: an English sentence pasted among the German copy.            */
/* ------------------------------------------------------------------ */

const PLACEHOLDER = /\{\{[^{}]*\}\}/g
const URL = /\b(?:https?:\/\/|www\.)\S+/gi
// English-only function words. Each is a form German does not have: the German
// counterpart ("und", "von", "dein", "welche") differs, so a hit is English.
const ENGLISH_ONLY =
  /\b(?:the|your|you|their|them|they|these|those|with|from|for|would|could|should|been|because|between|through|during|without|please|click|hover|its|were|are|is|has|have|and|or|of|into|onto|than|while|upon|within|which|whom|whose|does|don't|won't|can't|isn't|aren't|let's)\b/gi

export function englishSentenceWords(value: string): string[] {
  const prose = value.replace(PLACEHOLDER, ' ').replace(URL, ' ')
  return [...prose.matchAll(ENGLISH_ONLY)].map((m) => m[0].toLowerCase())
}

describe('the German surface', () => {
  it('reads German: no leaf is an unexplained copy of the English one', () => {
    expect(leaked).toEqual([])
  })

  it('names every same-by-design leaf once, and no leaf that has since changed', () => {
    // A stale entry is an exemption for a string that no longer needs one.
    expect(stale).toEqual([])
  })

  it('the design list stays a minority of the surface (it is not the whole file)', () => {
    expect(SAME_BY_DESIGN.size).toBeGreaterThan(40)
    expect(SAME_BY_DESIGN.size).toBeLessThan(deLeaves.length / 4)
  })

  it('holds no pasted English sentence', () => {
    const found = deLeaves
      .map(([key, value]) => [key, englishSentenceWords(value)] as const)
      .filter(([, words]) => words.length > 0)
      .map(([key, words]) => `${key}: ${words.join(', ')}`)
    expect(found).toEqual([])
  })
})

describe('the two detectors', () => {
  it('reports a leaf that copies its English neighbour', () => {
    const english = new Map([
      ['chat.newThing', 'Save changes'],
      ['chat.saved', 'Save changes'],
    ])
    const german: Array<[string, string]> = [
      ['chat.newThing', 'Save changes'],
      ['chat.saved', 'Änderungen gespeichert'],
    ]
    expect(unexplained(german, english, new Set())).toEqual([['chat.newThing', 'Save changes']])
  })

  it('accepts a copy that the design list names', () => {
    const pairs: Array<[string, string]> = [['settings.engine', 'Engine']]
    const english = new Map(pairs)
    expect(unexplained(pairs, english, new Set(['settings.engine']))).toEqual([])
  })

  it('catches an English sentence pasted among German copy', () => {
    expect(englishSentenceWords('Open the file with your changes')).toEqual(['the', 'with', 'your'])
  })

  it('leaves a German leaf and a placeholder alone', () => {
    expect(englishSentenceWords('Weiter zur Aufgabe')).toEqual([])
    expect(englishSentenceWords('Ephe {{from}} → {{to}}')).toEqual([])
    expect(englishSentenceWords('https://example.com/from/the/and')).toEqual([])
  })
})
