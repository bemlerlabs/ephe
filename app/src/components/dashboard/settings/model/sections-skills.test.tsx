// I7-4: skills grouped with a purpose line each, and the topic packs show their
// actual installation state rather than just their size.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { renderSkills } from './sections-capabilities'
import { renderPersona } from './sections-misc'
import type { SettingsModel } from './types'
import type { SkillPackInfo } from '@/lib/api/types'

const packs: SkillPackInfo[] = [
  {
    id: 'office-pack',
    title: 'Office',
    description: 'Documents.',
    complete: false,
    skills: [
      { name: 'pdf', installed: true, trigger: '/pdf' },
      { name: 'sheets', installed: false, trigger: '' },
      { name: 'decks', installed: false, trigger: '' },
    ],
  },
]

function skillModel(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    fileInputRef: { current: null },
    handleSkillDelete: () => {},
    handleSkillInstall: () => {},
    handleSkillInstallUrl: () => {},
    handleSkillToggle: () => {},
    packIndex: packs,
    reloadSkills: () => {},
    setSkillUrl: () => {},
    skillUrl: '',
    skills: [
      { name: 'pdf', description: 'Baut PDFs.', trigger: '/pdf', version: '1', is_builtin: false },
      {
        name: 'decks',
        description: 'Baut Foliensitze.',
        trigger: '/decks',
        is_builtin: true,
        disabled: true,
      },
    ],
    skillsBusy: false,
    skillsMsg: '',
    ...over,
  } as unknown as SettingsModel
}

function personaModel(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    personaLoading: false,
    personaSaving: false,
    personaSource: 'default',
    personaText: '',
    savePersona: () => {},
    setPersonaText: () => {},
    ...over,
  } as unknown as SettingsModel
}

describe('the skills area (I7-4)', () => {
  it('a pack shows how much of it is really installed', () => {
    render(renderSkills(skillModel()))
    expect(screen.getByTestId('pack-installed-office-pack').textContent).toContain(
      'settings.packInstalled',
    )
    expect(screen.getByTestId('pack-installed-office-pack').textContent).toContain('"have":1')
    expect(screen.getByTestId('pack-installed-office-pack').textContent).toContain('"total":3')
  })

  it('each group leads with its purpose line', () => {
    render(renderSkills(skillModel()))
    expect(screen.getByTestId('skills-group-packs').textContent).toContain(
      'settings.skillsGroupPacksHint',
    )
    expect(screen.getByTestId('skills-group-mine').textContent).toContain(
      'settings.skillsGroupMineHint',
    )
  })
})

describe('the persona area (I7-4)', () => {
  it('the internal path winner is not called default at the standard', () => {
    render(renderPersona(personaModel()))
    const line = screen.getByTestId('persona-source')
    expect(line.textContent).toContain('settings.personaSourceDefault')
    expect(line.textContent).not.toContain('default')
  })

  it('a real file is named with its path', () => {
    render(renderPersona(personaModel({ personaSource: '/Users/x/.ephe/persona.md' })))
    expect(screen.getByTestId('persona-source').textContent).toContain('/Users/x/.ephe/persona.md')
  })
})

describe('the origin of an installed skill (R4)', () => {
  const installed = [
    {
      name: 'pdf',
      description: 'Baut PDFs.',
      trigger: '/pdf',
      version: '1',
      is_builtin: false,
      install: {
        kind: 'url',
        origin: 'https://host.example/packs/pdf.zip',
        content_hash: 'sha256:aa',
      },
      unchanged: false,
    },
    { name: 'decks', description: 'Baut Foliensitze.', trigger: '/decks', is_builtin: true },
  ]

  it('shows the source and warns when the file is no longer the noted one', () => {
    render(renderSkills(skillModel({ skills: installed })))
    expect(screen.getByTestId('skill-origin-pdf').textContent).toBe(
      'https://host.example/packs/pdf.zip',
    )
    expect(screen.getByTestId('skill-changed-pdf')).toBeInTheDocument()
  })

  it('invents no source for a built-in skill', () => {
    render(renderSkills(skillModel({ skills: installed })))
    expect(screen.queryByTestId('skill-origin-decks')).toBeNull()
    expect(screen.queryByTestId('skill-changed-decks')).toBeNull()
  })
})
