// I3-V1: the matching icon for every settings field and every section.
//
// A register entry without its own glyph cannot be found in the list: every row is
// led by its icon, so every field needs one. The mapping lives here (and not in the backend
// register) because it is a UI decision: a field with no choice of its own falls
// back to the glyph of its type, never to nothing.
import {
  Activity,
  AlarmClock,
  Brain,
  CalendarClock,
  History,
  Copy,
  Filter,
  LoaderCircle,
  Clock3,
  Hourglass,
  Keyboard,
  Maximize2,
  RotateCcw,
  Rows3,
  ScrollText,
  Target,
  Thermometer,
  Wrench,
  BrainCircuit,
  Clock,
  Gauge,
  Hash,
  Webhook,
  ListChecks,
  MessagesSquare,
  Palette,
  PlayCircle,
  Puzzle,
  RefreshCw,
  ShieldCheck,
  Timer,
  Type,
  Layers,
  TextSelect,
} from 'lucide-react'

export type IconComponent = typeof Type

/** By field key — the row the user is looking for. */
export const FIELD_ICONS: Record<string, IconComponent> = {
  'chat.show_reasoning': BrainCircuit,
  'chat.details_mode': ListChecks,
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
  'memory.inject_max_entries': Layers,
  'memory.inject_min_score': Filter,
  'cron.misfire_grace_minutes': AlarmClock,
  'cron.history_keep': History,
  'cron.history_rows': ListChecks,
  'cron.max_parallel_jobs': Layers,
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
  ephemera: Hourglass,
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
  bool: ListChecks,
  number: Gauge,
  select: ListChecks,
  text: Type,
}

export function fieldIcon(key: string, type: string): IconComponent {
  return FIELD_ICONS[key] ?? TYPE_ICONS[type] ?? Type
}

export function sectionIcon(key: string): IconComponent | undefined {
  return SECTION_ICONS[key]
}
