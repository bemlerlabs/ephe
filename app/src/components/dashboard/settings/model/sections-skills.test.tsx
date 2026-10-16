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

describe('Skills-Bereich (I7-4)', () => {
  it('Pack zeigt, wie viel davon wirklich installiert ist', () => {
    render(renderSkills(skillModel()))
    expect(screen.getByTestId('pack-installed-office-pack').textContent).toContain(
      'settings.packInstalled',
    )
    expect(screen.getByTestId('pack-installed-office-pack').textContent).toContain('"have":1')
    expect(screen.getByTestId('pack-installed-office-pack').textContent).toContain('"total":3')
  })

  it('jede Gruppe fuehrt ihre Zweckzeile', () => {
    render(renderSkills(skillModel()))
    expect(screen.getByTestId('skills-group-install').textContent).toContain(
      'settings.skillsGroupInstallHint',
    )
    expect(screen.getByTestId('skills-group-packs').textContent).toContain(
      'settings.skillsGroupPacksHint',
    )
    expect(screen.getByTestId('skills-group-mine').textContent).toContain(
      'settings.skillsGroupMineHint',
    )
  })
})

describe('Persona-Bereich (I7-4)', () => {
  it('der interne Pfad-Gewinner heisst beim Standard nicht "default"', () => {
    render(renderPersona(personaModel()))
    const line = screen.getByTestId('persona-source')
    expect(line.textContent).toContain('settings.personaSourceDefault')
    expect(line.textContent).not.toContain('default')
  })

  it('eine echte Datei wird mit ihrem Pfad benannt', () => {
    render(renderPersona(personaModel({ personaSource: '/Users/x/.ephe/persona.md' })))
    expect(screen.getByTestId('persona-source').textContent).toContain('/Users/x/.ephe/persona.md')
  })
})

describe('Herkunft eines installierten Skills (R4)', () => {
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

  it('zeigt die Quelle und warnt, wenn die Datei nicht mehr die notierte ist', () => {
    render(renderSkills(skillModel({ skills: installed })))
    expect(screen.getByTestId('skill-origin-pdf').textContent).toBe(
      'https://host.example/packs/pdf.zip',
    )
    expect(screen.getByTestId('skill-changed-pdf')).toBeInTheDocument()
  })

  it('erfindet keine Quelle bei einem eingebauten Skill', () => {
    render(renderSkills(skillModel({ skills: installed })))
    expect(screen.queryByTestId('skill-origin-decks')).toBeNull()
    expect(screen.queryByTestId('skill-changed-decks')).toBeNull()
  })
})
