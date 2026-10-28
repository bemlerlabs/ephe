import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { SkillPackInfo } from '@/lib/api/types'
import { takeChatSeed } from '@/lib/chatSeed'
import type { SettingsModel } from './types'
import { renderSkills } from './sections-capabilities'

const { createSkill } = vi.hoisted(() => ({ createSkill: vi.fn(async () => ({ name: 'x' })) }))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, createSkill }
})

const pack: SkillPackInfo = {
  id: 'big',
  title: 'Big pack',
  description: 'Eight skills.',
  complete: false,
  skills: Array.from({ length: 8 }, (_, index) => ({
    name: `s${index}`,
    installed: false,
    trigger: `/s${index}`,
  })),
}

function model(over: Record<string, unknown> = {}) {
  return {
    t: (k: string, opts?: Record<string, unknown>) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
    i18n: { language: 'de' },
    fileInputRef: { current: null },
    handleSkillDelete: () => {},
    handleSkillInstall: () => {},
    handleSkillInstallUrl: () => {},
    handleSkillToggle: () => {},
    packIndex: [pack],
    reloadSkills: vi.fn(),
    setSkillUrl: () => {},
    skillUrl: '',
    skills: [
      { name: 'pdf', description: 'Baut PDFs.', trigger: '/pdf', version: '1', is_builtin: false },
    ],
    skillsBusy: false,
    skillsMsg: '',
    ...over,
  } as unknown as SettingsModel
}

afterEach(() => {
  window.location.hash = ''
  takeChatSeed()
  createSkill.mockClear()
})

describe('Skills Studio 2.0', () => {
  it('expands a pack from six skills to all of them', () => {
    render(renderSkills(model()))
    expect(screen.getByText('/s5')).toBeInTheDocument()
    expect(screen.queryByText('/s6')).toBeNull()
    fireEvent.click(screen.getByTestId('pack-expand-big'))
    expect(screen.getByText('/s6')).toBeInTheDocument()
    expect(screen.getByText('/s7')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('pack-expand-big'))
    expect(screen.queryByText('/s6')).toBeNull()
  })

  it('gives a skill its glyph and a one-click run chip', () => {
    render(renderSkills(model()))
    const row = screen.getByText('pdf').closest('div')!
    expect(row.querySelector('svg')).not.toBeNull()
    fireEvent.click(screen.getByTestId('skill-run-pdf'))
    expect(takeChatSeed()).toBe('/pdf')
    expect(window.location.hash).toBe('#/chat')
  })

  it('creates a skill from the builder card', async () => {
    render(renderSkills(model()))
    fireEvent.click(screen.getByTestId('skill-builder-toggle'))
    fireEvent.change(screen.getByTestId('skill-builder-name'), { target: { value: 'review' } })
    fireEvent.change(screen.getByTestId('skill-builder-trigger'), { target: { value: 'review' } })
    fireEvent.change(screen.getByTestId('skill-builder-description'), {
      target: { value: 'Reviews code.' },
    })
    fireEvent.change(screen.getByTestId('skill-builder-prompt'), {
      target: { value: 'Review the diff for security issues.' },
    })
    fireEvent.click(screen.getByTestId('skill-builder-create'))
    await waitFor(() => expect(createSkill).toHaveBeenCalledTimes(1))
    expect(createSkill).toHaveBeenCalledWith({
      name: 'review',
      trigger: '/review',
      description: 'Reviews code.',
      system_prompt: 'Review the diff for security issues.',
    })
    expect(await screen.findByTestId('skill-builder-note')).toHaveTextContent(
      'settings.skillBuilderCreated',
    )
  })
})
