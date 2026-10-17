/**
 * Ephe — lib/slashCommands.ts (Phase F2)
 *
 * GIVEN input typed into the chat composer
 * WHEN  parseSlashCommand() / filterCommands()
 * THEN  /compact, /new, /clear, /help are recognised; anything else = a normal message
 */
import { describe, it, expect, vi } from 'vitest'
import {
  parseSlashCommand,
  filterCommands,
  getSkillSlashCommands,
  loadSkillSlashCommands,
  SLASH_COMMANDS,
  PASSTHROUGH_COMMANDS,
  describeCommandDescription,
  buildHelpText,
  isAppCommand,
} from './slashCommands'

const listSkills = vi.hoisted(() => async () => ({
  skills: [
    { trigger: '/factory', description: 'Builds complete, runnable projects' },
    { trigger: '/doc-factory', description: 'Report-grade briefing PDFs' },
    { trigger: '/longdesc', description: 'x'.repeat(200) },
    { trigger: '/help', description: 'dup of a static command' },
    { trigger: '/factory', description: 'duplicate trigger' },
    { trigger: '', description: 'invalid' },
    null,
  ],
}))
const getPluginCommands = vi.hoisted(() => async () => ({
  commands: [
    {
      name: '/research',
      description: 'Run deep research',
      template: 'Research: {input}',
      plugin: 'research-suite',
    },
    {
      name: '/compact',
      description: 'dup of a static command',
      template: '',
      plugin: 'research-suite',
    },
  ],
}))
vi.mock('@/lib/api', () => ({ listSkills, getPluginCommands }))

describe('parseSlashCommand', () => {
  it('GIVEN /compact WHEN parse THEN action=compact, matched=true', () => {
    expect(parseSlashCommand('/compact')).toEqual({ matched: true, action: 'compact', rest: '' })
  })

  it('GIVEN /compact jetzt WHEN parse THEN action=compact + rest="jetzt"', () => {
    expect(parseSlashCommand('/compact jetzt')).toEqual({
      matched: true,
      action: 'compact',
      rest: 'jetzt',
    })
  })

  it('GIVEN /NEW WHEN parse THEN case-insensitiv action=new', () => {
    expect(parseSlashCommand('/NEW').action).toBe('new')
  })

  it('GIVEN /clear WHEN parse THEN action=clear', () => {
    expect(parseSlashCommand('/clear').action).toBe('clear')
  })

  it('GIVEN /help WHEN parse THEN action=help', () => {
    expect(parseSlashCommand('/help').action).toBe('help')
  })

  // G6: the newer commands
  it('GIVEN /model WHEN parse THEN action=model', () => {
    expect(parseSlashCommand('/model').action).toBe('model')
  })
  it('GIVEN /skills WHEN parse THEN action=skills', () => {
    expect(parseSlashCommand('/skills').action).toBe('skills')
  })
  it('GIVEN /sessions WHEN parse THEN action=sessions', () => {
    expect(parseSlashCommand('/sessions').action).toBe('sessions')
  })
  it('GIVEN /settings WHEN parse THEN action=settings', () => {
    expect(parseSlashCommand('/settings').action).toBe('settings')
  })

  it('GIVEN /unknown WHEN parse THEN matched=true aber action=null (UI meldet unbekannt)', () => {
    expect(parseSlashCommand('/unknown').action).toBeNull()
  })

  it('GIVEN normale Nachricht WHEN parse THEN matched=false (an Modell)', () => {
    expect(parseSlashCommand('Hallo Welt')).toMatchObject({ matched: false, action: null })
  })

  it("GIVEN 'Datei /compact.md öffnen' WHEN parse THEN matched=false (kein Wort am Anfang)", () => {
    expect(parseSlashCommand('Datei /compact.md öffnen').matched).toBe(false)
  })
})

describe('filterCommands', () => {
  it('GIVEN "/c" WHEN filter THEN compact+clear+context', () => {
    expect(filterCommands('/c').map((c) => c.cmd)).toEqual(['compact', 'clear', 'context'])
  })

  it('GIVEN "/" WHEN filter THEN alle Client- + Passthrough-Commands', () => {
    expect(filterCommands('/')).toHaveLength(SLASH_COMMANDS.length + PASSTHROUGH_COMMANDS.length)
  })

  it('GIVEN "/sw" WHEN filter THEN swarm (Passthrough sichtbar)', () => {
    expect(filterCommands('/sw').map((c) => c.cmd)).toContain('swarm')
  })

  it('GIVEN "/swarm task" WHEN parse THEN matched=true, action=null (Backend-Passthrough)', () => {
    const r = parseSlashCommand('/swarm Analysiere 3 Trends')
    expect(r.matched).toBe(true)
    expect(r.action).toBeNull()
    expect(r.rest).toBe('Analysiere 3 Trends')
  })

  it('GIVEN "/xyz" WHEN filter THEN leer', () => {
    expect(filterCommands('/xyz')).toHaveLength(0)
  })

  it('GIVEN "hallo" (kein Slash) WHEN filter THEN leer', () => {
    expect(filterCommands('hallo')).toHaveLength(0)
  })

  it('GIVEN extra skill commands WHEN filter "/fac" THEN /factory appears with description', () => {
    const extras = [
      { cmd: 'factory', label: '/factory', description: 'Builds complete, runnable projects' },
    ]
    const hits = filterCommands('/fac', extras)
    expect(hits.map((c) => c.cmd)).toContain('factory')
    expect(hits.find((c) => c.cmd === 'factory')!.description).toMatch(/runnable projects/)
  })

  it('GIVEN extra duplicates a static cmd WHEN filter THEN no duplicate entry', () => {
    const extras = [{ cmd: 'help', label: '/help', description: 'duplicate' }]
    const hits = filterCommands('/help', extras)
    expect(hits.filter((c) => c.cmd === 'help')).toHaveLength(1)
    expect(hits[0]!.description).not.toBe('duplicate')
  })

  it('GIVEN no extras WHEN filter THEN unchanged static behaviour', () => {
    expect(filterCommands('/sw').map((c) => c.cmd)).toEqual(
      filterCommands('/sw', []).map((c) => c.cmd),
    )
  })

  describe('loadSkillSlashCommands (R34)', () => {
    it('GIVEN backend skills WHEN load THEN factory entries join the menu, garbage skipped', async () => {
      await loadSkillSlashCommands()
      const cmds = getSkillSlashCommands().map((c) => c.cmd)
      expect(cmds).toContain('factory')
      expect(cmds).toContain('doc-factory')
      expect(cmds.filter((c) => c === 'factory')).toHaveLength(1) // dedupe
      expect(cmds).not.toContain('') // invalid triggers skipped, no crash on null entries
      // integration with the menu: static list stays intact, skill entry appears
      const menu = filterCommands('/', getSkillSlashCommands())
      const menuCmds = menu.map((c) => c.cmd)
      expect(menuCmds).toContain('factory') // skill entry joined
      expect(menuCmds).toContain('compact') // static list stays intact
      expect(menuCmds.filter((c) => c === 'factory')).toHaveLength(1)
    })

    it('GIVEN a skill that declares a built-in trigger WHEN loaded THEN the built-in stays the only row', async () => {
      await loadSkillSlashCommands()
      // the fixture carries a /help skill trigger; /help is a built-in command
      const cmds = getSkillSlashCommands().map((c) => c.cmd)
      expect(cmds).not.toContain('help')
      const menu = filterCommands('/', getSkillSlashCommands()).map((c) => c.cmd)
      expect(menu.filter((c) => c === 'help')).toHaveLength(1)
    })

    it('GIVEN every shipped command WHEN asked THEN the predicate names it, and a skill trigger fails it', () => {
      for (const c of [...SLASH_COMMANDS, ...PASSTHROUGH_COMMANDS]) {
        expect(isAppCommand(c.cmd)).toBe(true)
      }
      expect(isAppCommand('HELP')).toBe(true)
      expect(isAppCommand('factory')).toBe(false)
      expect(isAppCommand('')).toBe(false)
    })

    it('GIVEN second call WHEN load again THEN single fetch, stable set', async () => {
      const before = getSkillSlashCommands().length
      await loadSkillSlashCommands()
      expect(getSkillSlashCommands().length).toBe(before)
    })

    it('GIVEN manifest plugin commands WHEN loaded THEN they join the menu, static dupes win (E2)', async () => {
      await loadSkillSlashCommands()
      const extras = getSkillSlashCommands().map((c) => c.cmd)
      expect(extras).toContain('research') // plugin command joined
      const menu = filterCommands('/', getSkillSlashCommands()).map((c) => c.cmd)
      expect(menu).toContain('research')
      expect(menu.filter((c) => c === 'compact')).toHaveLength(1) // static wins the dupe
    })

    it('GIVEN 200-char description WHEN loaded THEN truncated with real ellipsis, not hard-cut', () => {
      // Judge R34 regression: a bare char-slice ended rows on dangling commas
      // mid-sentence when CSS truncate did not kick in (wide desktop rows).
      const entry = getSkillSlashCommands().find((c) => c.cmd === 'longdesc')
      expect(entry).toBeTruthy()
      expect(entry!.description.endsWith('…')).toBe(true)
      expect(entry!.description.length).toBeLessThanOrEqual(88)
      expect(entry!.description.trimEnd().endsWith(',')).toBe(false)
    })
  })
})

// ── I6 P3-1/P3-2: slash descriptions translated + /help multi-line stable ─────
// Finding: the command-menu rows and the /help list showed raw EN descriptions;
// the /help rows collapsed in Markdown into a single line.
describe('Slash-Beschreibungen + /help-Builder (I6 P3)', () => {
  const tStub = (key: string) => `T(${key})`

  it('jedes eingebaute Slash-Kommando traegt einen slash.desc.*-Key', () => {
    for (const c of [...SLASH_COMMANDS, ...PASSTHROUGH_COMMANDS]) {
      expect(c.descKey, c.cmd).toBeTruthy()
      expect(c.descKey!.startsWith('slash.desc.')).toBe(true)
    }
  })

  it('describeCommandDescription: mit descKey ueber t(), ohne descKey roh (Skills)', () => {
    expect(
      describeCommandDescription(
        { cmd: 'x', label: '/x', description: 'raw', descKey: 'slash.desc.x' },
        tStub,
      ),
    ).toBe('T(slash.desc.x)')
    expect(
      describeCommandDescription({ cmd: 'y', label: '/y', description: 'skill rohtext' }, tStub),
    ).toBe('skill rohtext')
  })

  it('buildHelpText: Markdown-Hartumbrueuche zwischen allen Kommando-Zeilen', () => {
    const out = buildHelpText(SLASH_COMMANDS, tStub)
    // A hard break = two spaces before the newline — so Markdown cannot collapse it.
    expect(out.includes('  ' + String.fromCharCode(10))).toBe(true)
    const breaks = out.split(String.fromCharCode(10)).length - 1
    expect(breaks).toBe(SLASH_COMMANDS.length - 1)
    expect(out).toContain('T(slash.desc.compact)')
    expect(out).not.toContain('Compact the context')
  })
})
