/**
 * Ephe — slash commands (phase F2)
 *
 * Client-side commands executed directly in the chat input (no backend call, no
 * model): /compact, /new, /clear, /help.
 *
 * Ponytail: reuse — `compactMessages` (lib/compact.ts) and the store actions
 * (createSession/clearSession) are not rebuilt, only driven. Parsing is
 * deterministic and unit-testable.
 */

export interface SlashCommand {
  cmd: string
  label: string
  description: string
  /**
   * I6 P3-2: i18n key (slash.desc.<cmd>) for the menu/help row. When missing
   * (e.g. server skills with their own raw text) => description is shown raw.
   */
  descKey?: string
}

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    cmd: 'compact',
    label: '/compact',
    description: 'Compact the context',
    descKey: 'slash.desc.compact',
  },
  { cmd: 'new', label: '/new', description: 'Start a new session', descKey: 'slash.desc.new' },
  { cmd: 'clear', label: '/clear', description: 'Clear this session', descKey: 'slash.desc.clear' },
  {
    cmd: 'model',
    label: '/model',
    description: 'Show the active model',
    descKey: 'slash.desc.model',
  },
  {
    cmd: 'skills',
    label: '/skills',
    description: 'List available skills',
    descKey: 'slash.desc.skills',
  },
  {
    cmd: 'sessions',
    label: '/sessions',
    description: 'Show sessions',
    descKey: 'slash.desc.sessions',
  },
  {
    cmd: 'memory',
    label: '/memory',
    description: 'Show semantic memory stats',
    descKey: 'slash.desc.memory',
  },
  {
    cmd: 'settings',
    label: '/settings',
    description: 'Open settings',
    descKey: 'slash.desc.settings',
  },
  {
    cmd: 'personality',
    label: '/personality',
    description: 'Edit the agent persona',
    descKey: 'slash.desc.personality',
  },
  {
    cmd: 'context',
    label: '/context',
    description: 'Show what the agent was told (prompt stages)',
    descKey: 'slash.desc.context',
  },
  {
    cmd: 'proposals',
    label: '/proposals',
    description: 'List patterns the agent wants to learn',
    descKey: 'slash.desc.proposals',
  },
  {
    cmd: 'accept',
    label: '/accept',
    description: 'Install a learning proposal as a skill: /accept <id>',
    descKey: 'slash.desc.accept',
  },
  {
    cmd: 'dismiss',
    label: '/dismiss',
    description: 'Ignore a learning proposal: /dismiss <id>',
    descKey: 'slash.desc.dismiss',
  },
  {
    cmd: 'help',
    label: '/help',
    description: 'Show available commands',
    descKey: 'slash.desc.help',
  },
  {
    cmd: 'companion',
    label: '/companion',
    description: 'Summon or rest the companion',
    descKey: 'slash.desc.companion',
  },
]

/**
 * Backend passthrough commands: NOT executed client-side but forwarded to the
 * backend (chat.py: /swarm → swarm pipeline, /learn → skill builder). They appear
 * only in the autocomplete; parseSlashCommand deliberately returns action:null so
 * ChatLayout passes them to handleSend (no client switch case).
 */
export const PASSTHROUGH_COMMANDS: SlashCommand[] = [
  {
    cmd: 'swarm',
    label: '/swarm',
    description: 'Multi-agent pipeline (parallel helpers)',
    descKey: 'slash.desc.swarm',
  },
  {
    cmd: 'learn',
    label: '/learn',
    description: 'Learn patterns and create a new skill',
    descKey: 'slash.desc.learn',
  },
]

/**
 * D3: the commands the app itself ships — the client-side ones plus the backend
 * passthroughs — as one set. A skill or a plugin is free to declare the same
 * trigger string, and that must never turn a built-in row into a skill row
 * (walkthrough: the /help row sat under the SKILLS heading, because the help
 * skill declares trigger "/help").
 */
const APP_COMMANDS = new Set(
  [...SLASH_COMMANDS, ...PASSTHROUGH_COMMANDS].map((c) => c.cmd.toLowerCase()),
)

/** True for a command the app defines itself, false for a skill or plugin trigger. */
export function isAppCommand(cmd: string): boolean {
  return APP_COMMANDS.has(
    String(cmd ?? '')
      .trim()
      .toLowerCase(),
  )
}

/**
 * I6 P3-2: description text of a command in the active language.
 * Translated via descKey, raw without one — pure, so unit-testable.
 *
 * The raw text doubles as the fallback because a skill's description arrives from
 * its own SKILL.md, in whatever language that file was written in. i18next answers
 * an unknown key with the key itself, so a lookup without `defaultValue` would put
 * `skills.desc.api-tester` on the screen — a worse surface than the German line it
 * was meant to replace.
 */
export function describeCommandDescription(
  c: Partial<SlashCommand> & { description: string },
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  return c.descKey ? t(c.descKey, { defaultValue: c.description }) : c.description
}

/**
 * The locale slot a skill's description resolves through: `skills.desc.<name>`.
 * The name is the SKILL.md `name`, which is the directory name — a lowercase slug,
 * never containing a dot, so it survives i18next's key separator.
 */
export function skillDescriptionKey(name: string): string {
  return `skills.desc.${String(name ?? '')
    .trim()
    .toLowerCase()}`
}

/**
 * One skill's description for a reader. The key rule sits here, next to
 * `describeCommandDescription`, because the same line is shown in three surfaces
 * (the slash menu, the `/skills` row in the transcript, the register's Skills
 * list) and two of them can drift from the third in silence.
 */
export function describeSkill(
  s: { name?: string; description?: string },
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const raw = String(s?.description ?? '')
  const key = skillDescriptionKey(String(s?.name ?? ''))
  // No name means there is no slot to look in — the file text is all there is.
  return key === 'skills.desc.' ? raw : t(key, { defaultValue: raw })
}

/**
 * I6 P3-1: the /help command list as Markdown text. The rows are separated with a
 * hard line break (two spaces + newline) — plain newlines collapse to ONE line in
 * the Markdown renderer (deep-test finding).
 */
export function buildHelpText(
  commands: (Partial<SlashCommand> & { label: string; description: string })[],
  t: (key: string) => string,
): string {
  return commands
    .map((c) => `${c.label} — ${describeCommandDescription(c, t)}`)
    .join(`  ${String.fromCharCode(10)}`)
}

export type SlashAction =
  | 'compact'
  | 'new'
  | 'clear'
  | 'model'
  | 'skills'
  | 'sessions'
  | 'memory'
  | 'settings'
  | 'personality'
  | 'context'
  | 'proposals'
  | 'accept'
  | 'dismiss'
  | 'help'
  | 'companion'

export interface SlashParseResult {
  matched: boolean
  action: SlashAction | null
  /** Input message (for /help etc., otherwise empty) */
  rest: string
}

/**
 * Parse the input: only when the message starts with `/cmd` at the beginning
 * (whole word, no `/` in the middle). Otherwise → `matched: false` (normal
 * message). Unknown `/xyz` → `matched: true, action: null` so the UI can report
 * "unknown" instead of sending it to the model.
 */
export function parseSlashCommand(input: string): SlashParseResult {
  const trimmed = input.trim()
  if (!trimmed.startsWith('/')) {
    return { matched: false, action: null, rest: '' }
  }
  const spaceIdx = trimmed.indexOf(' ')
  const head = (spaceIdx === -1 ? trimmed : trimmed.slice(0, spaceIdx))
    .toLowerCase()
    .replace(/^\//, '')
  const rest = spaceIdx === -1 ? '' : trimmed.slice(spaceIdx + 1).trim()

  const known = SLASH_COMMANDS.find((c) => c.cmd === head)
  return {
    matched: true,
    action: known ? (known.cmd as SlashAction) : null,
    rest,
  }
}

/** Autocomplete suggestions: every command (client + passthrough) starting with the current input. */
export function filterCommands(input: string, extraCommands: SlashCommand[] = []): SlashCommand[] {
  const q = input.trim().toLowerCase()
  if (!q.startsWith('/')) return []
  const head = q.replace(/^\/+/, '').split(' ')[0] ?? ''
  const statics = [...SLASH_COMMANDS, ...PASSTHROUGH_COMMANDS]
  const extras = extraCommands.filter((c) => c && c.cmd && !isAppCommand(c.cmd))
  return [...statics, ...extras].filter((c) => c.cmd.startsWith(head))
}

// ── R34: skill triggers in the autocomplete ─────────────────────────────────
// The slash menu knew only static commands so far; skill triggers (/pdf,
// /factory …) worked only if you already knew their name. Loaded once from
// GET /api/skills (dynamic import — keeps the components tests' api mock out of
// the import graph), deduplicated against the static commands, offline-capable:
// quietly falls back to [].
const skillCommands: SlashCommand[] = []
let skillCommandsLoaded = false

export function getSkillSlashCommands(): SlashCommand[] {
  // Snapshot copy: loadSkillSlashCommands mutates in place, and React bails
  // out of state updates / memo recomputes on identical references. Returning
  // the same array forever would leave consumers stuck on the first snapshot.
  return [...skillCommands]
}

export async function loadSkillSlashCommands(): Promise<void> {
  if (skillCommandsLoaded) return
  skillCommandsLoaded = true
  try {
    const api = await import('@/lib/api')
    const res = await api.listSkills?.()
    const skills: Array<{ name?: string; trigger?: string; description?: string }> =
      res?.skills ?? []
    for (const s of skills) {
      const trig = String(s?.trigger ?? '')
        .trim()
        .toLowerCase()
      if (!trig.startsWith('/') || trig.length < 2) continue
      const cmd = trig.slice(1).split(/[ /]/)[0]
      // A built-in command keeps its own row: a skill trigger with the same
      // token must not shadow it (D3, the /help skill).
      if (!cmd || isAppCommand(cmd) || skillCommands.some((c) => c.cmd === cmd)) continue
      // Slice with a real ellipsis on a word boundary: a bare char-slice
      // hard-cuts mid-sentence whenever CSS truncate does not kick in (wide
      // desktop rows fit the budget and would end on a dangling comma).
      const desc = String(s?.description ?? '')
      let shown = desc
      if (desc.length > 88) {
        const cut = desc.slice(0, 87)
        const space = cut.lastIndexOf(' ')
        shown = (space > 40 ? cut.slice(0, space) : cut).trimEnd() + '…'
      }
      skillCommands.push({
        cmd,
        label: trig,
        description: shown,
        // The SKILL.md line stays as the fallback; a locale entry in the reader's
        // language wins over it. See `skillDescriptionKey`.
        descKey: skillDescriptionKey(s?.name ?? cmd),
      })
    }
    // E2: manifest-declared slash commands of ACTIVE plugins join the menu —
    // same dedupe, template lives server-side (the backend expands it).
    const pc = await api.getPluginCommands?.()
    for (const c of pc?.commands ?? []) {
      const name = String(c?.name ?? '')
        .trim()
        .toLowerCase()
      if (!name.startsWith('/') || name.length < 2) continue
      const cmd = name.slice(1)
      if (!cmd || isAppCommand(cmd) || skillCommands.some((x) => x.cmd === cmd)) continue
      skillCommands.push({ cmd, label: name, description: String(c?.description ?? '') })
    }
  } catch {
    // Backend offline, or api mocked without listSkills → autocomplete stays static.
  }
}
