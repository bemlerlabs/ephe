'use client'

/**
 * Settings hub (P5) — AI-client pattern: a slide-over with a left nav column
 * instead of a tab strip. The sections bundle what already existed (engine =
 * model+API, cron jobs = SchedulerPanel, artifacts = session activities, tasks =
 * /api/tasks) and was previously scattered across the chat.
 */

export interface SettingsPanelProps {
  isOpen: boolean
  onClose: () => void
  /** Deep link into a section (e.g. 'mobile' from the header QR button). */
  initialTab?: TabKey
}

export type TabKey =
  | 'engine'
  | 'appearance'
  | 'behaviour'
  | 'generation'
  | 'skills'
  | 'cron'
  | 'artifacts'
  | 'tasks'
  | 'voice'
  | 'memory'
  | 'persona'
  | 'mobile'
  | 'language'
  | 'privacy'
  | 'about'
  | 'mcp'
  | 'plugins'
  | 'hooks'
  | 'code-exec'
  | 'shortcuts'
  | 'network'
  | 'ephemera'
  | 'ephemeris'

// W10: the navigation's tab rows in display order — the ONE list. model.tsx pairs
// these keys with their icons and exports NAV; the command palette
// (hooks/paletteExtraItems.ts) reads the same keys. It sits in this import-free
// module on purpose: a hook importing model.tsx would close an import cycle
// (model.tsx → sections → components/ui → hooks/useCommandPalette).
export const NAV_KEYS = [
  'engine',
  'appearance',
  'behaviour',
  'generation',
  'skills',
  'cron',
  'artifacts',
  'ephemera',
  'ephemeris',
  'tasks',
  'voice',
  'memory',
  'persona',
  'mobile',
  'language',
  'privacy',
  'about',
  'plugins',
  'hooks',
  'code-exec',
  'shortcuts',
  'network',
  'mcp',
] as const

// DD-24: pure view / instant-effect tabs — there is nothing to save here (language
// persists on click via updateSettings, about is information only, ephemeris is the
// pure sky area: orbits + token usage, read-only).
// Otherwise the save bar stayed behind as a dead button.
// I5-4: artifacts/tasks follow the same rule — artifacts and hooks persist on click
// through their own endpoints. (cron no longer belongs here: since I7-3 the four
// schedule sliders live in that tab, which the footer button has to save.)
// I7-4: same for skills, mcp, persona — disabling, the server list and the persona
// write their own file immediately (skills_state.json, mcp.json, persona.md).
// The footer used to save the engine while the user was touching something else.
// I7-6: and audio + mobile — every slider there persists on change or on losing
// focus, the cards do it when the token is saved.
export const READONLY_TABS: ReadonlySet<TabKey> = new Set([
  // I6-5/6: network is a read-only surface. Shortcuts stays a read board except
  // the desktop's global opt-in, which the register owns (Wave 6).
  'network',
  // I6-4: the lids are measured, not set — the footer button saved the engine
  // while the user was looking at a read-only board.
  'code-exec',
  // I6-8: same for privacy — the approval profile, sandbox and read-aloud persist
  // on click through their own endpoints. The footer saved the engine while the
  // user was touching an approval profile.
  'privacy',
  'about',
  'language',
  'ephemeris',
  'artifacts',
  'tasks',
  'skills',
  'mcp',
  'persona',
  'voice',
  'mobile',
])

export const VOICES = [
  { id: 'de-DE-KillianNeural', labelKey: 'settings.voiceKillian' },
  { id: 'de-DE-KatjaNeural', labelKey: 'settings.voiceKatja' },
  { id: 'de-DE-ConradNeural', labelKey: 'settings.voiceConrad' },
  { id: 'en-US-AriaNeural', labelKey: 'settings.voiceAria' },
  { id: 'en-US-GuyNeural', labelKey: 'settings.voiceGuy' },
]
