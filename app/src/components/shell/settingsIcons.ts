// I3-V1: the matching icon for every settings field and every section.
//
// A register entry without its own glyph cannot be found in the list: every row is
// led by its icon, so every field needs one. The mapping lives here (and not in the backend
// register) because it is a UI decision: a field with no choice of its own falls
// back to the glyph of its type, never to nothing.
//
// One glyph, one row: two fields sharing an icon makes the list unreadable at a
// glance, which is what the icon is there for. `auditSettingsIconCollisions` is the
// check for that, and the test beside this file holds it to zero.
import {
  Activity,
  AlarmClock,
  Archive,
  Brain,
  CalendarClock,
  ChevronsUpDown,
  Clock,
  Clock3,
  Copy,
  DatabaseZap,
  Eye,
  Filter,
  Gauge,
  GitFork,
  Hash,
  History,
  Hourglass,
  Keyboard,
  LoaderCircle,
  Maximize2,
  MessagesSquare,
  Orbit,
  Palette,
  PlayCircle,
  Puzzle,
  RefreshCw,
  RotateCcw,
  Rows3,
  ScrollText,
  ShieldCheck,
  Target,
  TextCursorInput,
  TextSelect,
  Thermometer,
  Timer,
  ToggleLeft,
  Type,
  Webhook,
  Wrench,
  BrainCircuit,
} from 'lucide-react'

export type IconComponent = typeof Type

/** By field key — the row the user is looking for. */
export const FIELD_ICONS: Record<string, IconComponent> = {
  'chat.show_reasoning': BrainCircuit,
  'chat.details_mode': Eye,
  // I6-3: the behaviour area. A field without its own glyph would fall back to its
  // type's — in a list the user reads by icon, that is the emergency exit, not the
  // rule.
  'chat.allow_input_while_streaming': Keyboard,
  'chat.show_tool_count': Hash,
  'chat.expand_tool_calls': Rows3,
  'chat.show_thinking_loader': LoaderCircle,
  'chat.stream_idle_seconds': Hourglass,
  'chat.duration_format': Clock3,
  'chat.tool_result_chars': ScrollText,
  'chat.continue_attempts': RotateCcw,
  'memory.capture_enabled': Brain,
  'memory.capture_min_answer_chars': TextSelect,
  'memory.dedupe_score_threshold': Copy,
  'memory.inject_max_entries': DatabaseZap,
  'memory.inject_min_score': Filter,
  'cron.misfire_grace_minutes': AlarmClock,
  'cron.history_keep': Archive,
  'cron.history_rows': History,
  'cron.max_parallel_jobs': GitFork,
  'hooks.enabled': Webhook,
  'appearance.font_scale': Type,
  'appearance.animations_enabled': Activity,
  'appearance.show_timestamps': Clock,
  'appearance.update_check': RefreshCw,
  'advanced.api_timeout': Timer,
  'plugins.plugin_autorun': PlayCircle,
  'plugins.plugin_signature_check': ShieldCheck,
}

/** By register section — the group header above the rows. */
export const SECTION_ICONS: Record<string, IconComponent> = {
  chat: MessagesSquare,
  appearance: Palette,
  advanced: Gauge,
  plugins: Puzzle,
  memory: Brain,
  ephemera: Orbit,
  cron: CalendarClock,
  hooks: Webhook,
}

/** The six generation levers on the engine card. */
export const GENERATION_ICONS: Record<string, IconComponent> = {
  temperature: Thermometer,
  top_p: Target,
  max_tokens: Hash,
  tool_budget: Wrench,
  context_window: Maximize2,
  memory_max_entries: Brain,
}

export function generationIcon(key: string): IconComponent {
  return GENERATION_ICONS[key] ?? Hash
}

const TYPE_ICONS: Record<string, IconComponent> = {
  bool: ToggleLeft,
  number: Gauge,
  select: ChevronsUpDown,
  text: TextCursorInput,
}

export function fieldIcon(key: string, type: string): IconComponent {
  return FIELD_ICONS[key] ?? TYPE_ICONS[type] ?? Type
}

export function sectionIcon(key: string): IconComponent | undefined {
  return SECTION_ICONS[key]
}

export interface IconCollision {
  icon: string
  keys: string[]
}

/**
 * Two rows wearing the same glyph. Field keys and type fallbacks share one
 * namespace because they share one list; section headers are a different surface
 * and are not counted here.
 */
export function auditSettingsIconCollisions(): IconCollision[] {
  const byIcon = new Map<string, string[]>()
  const rows = [...Object.entries(FIELD_ICONS), ...Object.entries(TYPE_ICONS)]
  for (const [key, icon] of rows) {
    const name = icon.displayName ?? 'anonymous'
    const keys = byIcon.get(name)
    if (keys) keys.push(key)
    else byIcon.set(name, [key])
  }
  return [...byIcon.entries()]
    .filter(([, keys]) => keys.length > 1)
    .map(([icon, keys]) => ({ icon, keys }))
}
