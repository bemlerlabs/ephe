// SettingsPanel logic layer — composition (wave 3b, modularised into model/*).
'use client'

/**
 * Settings hub (P5) — AI-client pattern: a slide-over with a left nav column
 * instead of a tab bar. The logic is split into model/* submodules; this file pairs
 * the navigation's tab keys (NAV_KEYS in ./types — the one list, read by the command
 * palette too) with their icons and joins the sub-hooks into useSettingsPanelModel
 * via buildModel + the render* sections.
 */
import * as React from 'react'
import {
  Zap,
  Activity,
  Brain,
  Languages,
  Shield,
  Smartphone,
  Volume2,
  CalendarClock,
  FileBox,
  ListTodo,
  Info,
  Wrench,
  UserRound,
  Plug,
  Webhook,
  SlidersHorizontal,
  Store,
  Terminal,
  Keyboard,
  Globe,
  Palette,
  MoonStar,
  Hourglass,
  Bot,
  UsersRound,
} from 'lucide-react'
import type { TabKey } from './types'
import type { SettingsPanelProps } from './types'
import { NAV_KEYS } from './types'
import { useSettingsModel } from './model/buildModel'
import { EngineSection } from './model/sections-engine'
import { renderGeneration } from './model/sections-generation'
import { renderSkills, renderCron, renderArtifacts } from './model/sections-capabilities'
import { renderTasks } from './model/sections-tasks'
import { renderMobile } from './model/sections-io'
import { VoiceSection } from './model/sections-voice'
import { MemorySection } from './model/sections-memory'
import { EphemeraSection } from './model/sections-ephemera'
import {
  renderPersona,
  renderLanguage,
  renderPrivacy,
  renderAbout,
  renderEphemeris,
} from './model/sections-misc'
import { renderMcp } from './model/sections-mcp'
import { renderPlugins } from './model/sections-plugins'
import { AppearanceSection } from './model/sections-appearance'
import { HooksSection } from './model/sections-hooks'
import { CodeExecSection } from './model/sections-code-exec'
import { ShortcutsSection } from './model/sections-shortcuts'
import { NetworkSection } from './model/sections-network'
import { BehaviourSection } from './model/sections-behaviour'

// Agent Center and Teams are their own lazy chunks: a reader who opens Engine
// should not download two editors. The settings register is already a route
// chunk; these are the second split inside it.
const AgentsSection = React.lazy(() => import('./model/sections-agents'))
const TeamsSection = React.lazy(() => import('./model/sections-teams'))

function SectionSkeleton() {
  return <div className="h-24 animate-pulse rounded-xl bg-surface/40" aria-hidden="true" />
}

export type { SettingsPanelProps, TabKey } from './types'
export { VOICES } from './types'
export { providerLabel, languageOptions } from './model/constants'
export type { SettingsModel } from './model/buildModel'

// W10: the keys are the one list (NAV_KEYS in ./types) — the same rows the command
// palette offers. Only the icons live here, so the order and the set cannot diverge.
const NAV_ICON: Record<TabKey, React.ComponentType<{ className?: string }>> = {
  engine: Zap,
  appearance: Palette,
  behaviour: Activity,
  generation: SlidersHorizontal,
  skills: Wrench,
  cron: CalendarClock,
  agents: Bot,
  teams: UsersRound,
  artifacts: FileBox,
  ephemera: Hourglass,
  ephemeris: MoonStar,
  tasks: ListTodo,
  voice: Volume2,
  memory: Brain,
  persona: UserRound,
  mobile: Smartphone,
  language: Languages,
  privacy: Shield,
  about: Info,
  plugins: Store,
  hooks: Webhook,
  'code-exec': Terminal,
  shortcuts: Keyboard,
  network: Globe,
  mcp: Plug,
}

export const NAV: { key: TabKey; icon: React.ComponentType<{ className?: string }> }[] =
  NAV_KEYS.map((key) => ({ key, icon: NAV_ICON[key] }))

// The four groups of the register (docs/SCREEN_SPEC.md §7). About is the
// dashed closing card below them, without a fifth heading.
export const NAV_GROUPS: { groupKey: string; keys: TabKey[] }[] = [
  {
    groupKey: 'settings.groupEveryday',
    keys: ['language', 'appearance', 'behaviour', 'shortcuts'],
  },
  {
    groupKey: 'settings.groupCapabilities',
    keys: [
      'engine',
      'generation',
      'voice',
      'memory',
      'persona',
      'skills',
      'cron',
      'agents',
      'teams',
    ],
  },
  {
    groupKey: 'settings.groupData',
    keys: ['privacy', 'artifacts', 'tasks', 'ephemeris', 'mobile'],
  },
  {
    groupKey: 'settings.groupAdvanced',
    keys: ['mcp', 'plugins', 'hooks', 'code-exec', 'ephemera', 'network'],
  },
]

export const ABOUT_KEYS: TabKey[] = ['about']

// IcoEphemora lookup for the group nav (one icon per row, no rows without an icon).
export function navIcon(key: TabKey): React.ComponentType<{ className?: string }> {
  return NAV_ICON[key] ?? Info
}

// The order of the expert register comes from the server (core/settings_schema.py
// ::SECTIONS) — a second list here was only another place where things could
// diverge (it named 'safety', which has not existed since I3-1, and was never
// read).

export function useSettingsPanelModel(props: SettingsPanelProps) {
  const model = useSettingsModel(props)

  const section: Record<TabKey, React.ReactNode> = {
    engine: <EngineSection model={model} />,
    appearance: <AppearanceSection model={model} />,
    behaviour: <BehaviourSection model={model} />,
    generation: renderGeneration(model),
    skills: renderSkills(model),
    cron: renderCron(model),
    agents: (
      <React.Suspense fallback={<SectionSkeleton />}>
        <AgentsSection model={model} />
      </React.Suspense>
    ),
    teams: (
      <React.Suspense fallback={<SectionSkeleton />}>
        <TeamsSection model={model} />
      </React.Suspense>
    ),
    artifacts: renderArtifacts(model),
    ephemeris: renderEphemeris(model),
    tasks: renderTasks(model),
    voice: <VoiceSection model={model} />,
    memory: <MemorySection model={model} />,
    ephemera: <EphemeraSection model={model} />,
    persona: renderPersona(model),
    mobile: renderMobile(model),
    language: renderLanguage(model),
    privacy: renderPrivacy(model),
    about: renderAbout(model),
    plugins: renderPlugins(model),
    hooks: <HooksSection model={model} />,
    'code-exec': <CodeExecSection model={model} />,
    shortcuts: <ShortcutsSection model={model} />,
    network: <NetworkSection model={model} />,
    mcp: renderMcp(model),
  }

  return { ...model, section }
}
