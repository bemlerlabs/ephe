/**
 * D4, surface 1: a skill's description reaches the reader in their language, and
 * an untranslated one still reads as text rather than as a key.
 *
 * The count this exists for: 51 SKILL.md files, 3 descriptions the repo's own
 * instrument counts as German (`api-tester`, `code-metrics`, `config-setup`), and
 * `skills/` is in `PROTECTED_PREFIXES`, so the language gate never looked at them —
 * which is how a German line ended up inside the English register. The mechanism is
 * the one `reader.*` and `slash.desc.*` already use: a stable key, both locales, the
 * raw file text as fallback.
 *
 * These run against the real i18next instance, because the thing being proven is
 * `defaultValue` resolution — a stub would only prove the branch we wrote.
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import i18n from '@/i18n'
import { describeCommandDescription, describeSkill, skillDescriptionKey } from './slashCommands'
import en from '@/locales/en.json'
import de from '@/locales/de.json'

const GERMAN_SOURCE = 'Fuehrt HTTP-Requests aus und prueft Status, Latenz und JSON-Schema.' // language-gate: ignore (the measured SKILL.md line under test)

/**
 * WD-33: each catalog is a chunk of its own and `i18n.ts` boots with the one the stored
 * language needs, so `lng: 'de'` alone reads nothing here — `catalogBackend` answers the
 * boot language and the language a switch is heading to, and no other. German therefore
 * enters the store the way it does in the app: through the switch, once, before the
 * assertions. Both languages are resident from here on, and every case below still reads
 * the real i18next store.
 */
beforeAll(async () => {
  await i18n.changeLanguage('de')
})

// `skillDescriptionKey` is string formatting: the key it returns needs no catalog.
describe('skillDescriptionKey', () => {
  it('is the skill name, lowercased and trimmed, under skills.desc', () => {
    expect(skillDescriptionKey('api-tester')).toBe('skills.desc.api-tester')
    expect(skillDescriptionKey('  Code-Metrics ')).toBe('skills.desc.code-metrics')
    expect(skillDescriptionKey('')).toBe('skills.desc.')
  })
})

describe('describeCommandDescription with a live i18next', () => {
  // `lng` per call instead of `changeLanguage`: the switch is async, and an explicit `lng`
  // keeps each assertion independent of the language the instance happens to sit in.
  const resolve = (row: Parameters<typeof describeCommandDescription>[0], lng: 'en' | 'de') =>
    describeCommandDescription(row, (k, o) => i18n.t(k, { ...o, lng }))

  it('answers in the reader language when the locale carries the key', () => {
    const row = {
      cmd: 'api-test',
      label: '/api-test',
      description: GERMAN_SOURCE,
      descKey: skillDescriptionKey('api-tester'),
    }
    expect(resolve(row, 'en')).toBe(en.skills.desc['api-tester'])
    expect(resolve(row, 'de')).toBe(de.skills.desc['api-tester'])
    expect(resolve(row, 'en')).not.toContain('Fuehrt')
  })

  it('falls back to the SKILL.md line when no locale carries it', () => {
    const row = {
      cmd: 'pdf',
      label: '/pdf',
      description: 'Builds a PDF from the text you give it.',
      descKey: skillDescriptionKey('pdf'),
    }
    expect(resolve(row, 'en')).toBe(row.description)
    expect(resolve(row, 'de')).toBe(row.description)
  })

  it('never puts the key on the screen for a skill without an entry', () => {
    const out = resolve(
      {
        cmd: 'x',
        label: '/x',
        description: 'raw text',
        descKey: skillDescriptionKey('no-such-skill'),
      },
      'en',
    )
    expect(out).toBe('raw text')
    expect(out).not.toContain('skills.desc.')
  })

  it('leaves a command without a key exactly as it came', () => {
    expect(resolve({ cmd: 'y', label: '/y', description: 'plugin text' }, 'en')).toBe('plugin text')
  })
})

describe('skills.desc locale parity', () => {
  const keys = Object.keys(en.skills.desc)
  it('has 3 entries, one per untranslated skill', () => {
    expect(keys.sort()).toEqual(['api-tester', 'code-metrics', 'config-setup'])
  })

  it('carries every key in both languages', () => {
    for (const k of keys) {
      expect(
        de.skills.desc[k as keyof typeof de.skills.desc],
        `de.json lacks skills.desc.${k}`,
      ).toBeTruthy()
    }
    expect(Object.keys(de.skills.desc).sort()).toEqual(keys)
  })

  it('answers the English interface with a different sentence than the German one', () => {
    for (const k of keys) {
      expect(en.skills.desc[k as keyof typeof en.skills.desc]).toBeTruthy()
      expect(en.skills.desc[k as keyof typeof en.skills.desc]).not.toBe(
        de.skills.desc[k as keyof typeof de.skills.desc],
      )
    }
  })
})

describe('describeSkill — the transcript and register path', () => {
  const resolve = (s: { name?: string; description?: string }, lng: 'en' | 'de') =>
    describeSkill(s, (k, o) => i18n.t(k, { ...o, lng }))

  it('reads the locale entry for a skill that has one', () => {
    expect(resolve({ name: 'config-setup', description: 'Gefuehrter Setup-Dialog' }, 'en')).toBe(
      en.skills.desc['config-setup'],
    )
    expect(resolve({ name: 'config-setup', description: 'Gefuehrter Setup-Dialog' }, 'de')).toBe(
      de.skills.desc['config-setup'],
    )
  })

  it('reads the file text for a skill without an entry, in either language', () => {
    const s = { name: 'pdf', description: 'Builds a PDF from the text you give it.' }
    expect(resolve(s, 'en')).toBe(s.description)
    expect(resolve(s, 'de')).toBe(s.description)
  })

  it('shows nothing but the file text when there is no name to key on', () => {
    expect(resolve({ description: 'nameless' }, 'en')).toBe('nameless')
    expect(resolve({}, 'en')).toBe('')
  })
})

describe('the surfaces agree', () => {
  // The transcript row is built inside a hook, so the contract is held as a
  // source rule: the list must go through the resolver, not the raw field.
  const MODEL = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '../components/dashboard/chat/model.ts'),
    'utf8',
  )

  it('builds the /skills transcript row through describeSkill', () => {
    const line = MODEL.split('\n').find(
      (l) => l.includes('chat.skillList') || l.includes('• ${s.name}'),
    )
    expect(line, 'the /skills list line moved out of model.ts').toContain('describeSkill(s, t)')
    expect(line).not.toContain('${s.description}')
  })

  const REGISTER = readFileSync(
    join(
      dirname(fileURLToPath(import.meta.url)),
      '../components/dashboard/settings/model/sections-capabilities.tsx',
    ),
    'utf8',
  )

  it('renders the register skill row through describeSkill', () => {
    expect(REGISTER).toContain('{describeSkill(s, t)}')
    expect(REGISTER).not.toContain('{s.description}')
  })
})
