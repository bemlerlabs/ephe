/**
 * The approval profile register: four values, all of them chosen in the UI.
 *
 * Walkthrough 2026-10-12 (medium): the code knows four profiles — `strict`,
 * `session`, `plan`, `full` (core/security_config.py::VALID_APPROVAL_PROFILES) —
 * and the settings surface rendered two buttons for them, so a user could not
 * select a state the server would accept. Held here: one radio per profile, the
 * click hands the profile value to the save call, and the row carries the
 * sentence that says how this profile and the composer mode relate.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import en from '@/locales/en.json'

const read = (key: string): string | undefined => {
  let node: unknown = en
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return undefined
    node = (node as Record<string, unknown>)[part]
  }
  return typeof node === 'string' ? node : undefined
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: { defaultValue?: string }) => read(key) ?? opts?.defaultValue ?? key,
  }),
}))

import { ApprovalRegister } from './approvalRegister'
import type { SettingsModel } from './types'

const PROFILES = ['strict', 'session', 'plan', 'full'] as const

function privacyModel(profile: string) {
  const handleSecuritySave = vi.fn(async () => undefined)
  const model = {
    t: (key: string, opts?: { defaultValue?: string }) => read(key) ?? opts?.defaultValue ?? key,
    confirmClearLocal: false,
    setConfirmClearLocal: vi.fn(),
    securityCfg: { approval_profile: profile, sandbox_enabled: false },
    handleSecuritySave,
  } as unknown as SettingsModel
  return { model, handleSecuritySave }
}

describe('the approval profile row', () => {
  it.each(PROFILES)('offers %s as a choice the code accepts', (profile) => {
    const { model } = privacyModel('strict')
    render(<ApprovalRegister model={model} />)
    const radio = screen.getByTestId(`security-profile-${profile}`)
    expect(radio.getAttribute('role')).toBe('radio')
    expect(radio.textContent?.trim().length ?? 0).toBeGreaterThan(0)
  })

  it('hands the chosen profile to the save call', () => {
    const { model, handleSecuritySave } = privacyModel('strict')
    render(<ApprovalRegister model={model} />)
    fireEvent.click(screen.getByTestId('security-profile-full'))
    expect(handleSecuritySave).toHaveBeenCalledWith({ approval_profile: 'full' })
  })

  it('offers the two ask-more categories and adds one without dropping the other', () => {
    // Wave 2/B3: the override may only raise. The two categories that auto-run are
    // the two offered; the other two already prompt.
    const { model, handleSecuritySave } = privacyModel('strict')
    model.securityCfg = {
      approval_profile: 'strict',
      sandbox_enabled: false,
      ask_categories: ['SAFE'],
    }
    render(<ApprovalRegister model={model} />)
    expect(screen.getByTestId('privacy-ask-safe')).toBeTruthy()
    expect(screen.getByTestId('privacy-ask-network')).toBeTruthy()
    expect(screen.queryByTestId('privacy-ask-mutating')).toBeNull()
    fireEvent.click(screen.getByTestId('ask-network-toggle'))
    expect(handleSecuritySave).toHaveBeenCalledWith({ ask_categories: ['SAFE', 'NETWORK'] })
  })

  it('removes a category again without touching the other', () => {
    const { model, handleSecuritySave } = privacyModel('strict')
    model.securityCfg = {
      approval_profile: 'strict',
      sandbox_enabled: false,
      ask_categories: ['SAFE', 'NETWORK'],
    }
    render(<ApprovalRegister model={model} />)
    fireEvent.click(screen.getByTestId('ask-safe-toggle'))
    expect(handleSecuritySave).toHaveBeenCalledWith({ ask_categories: ['NETWORK'] })
  })

  it('marks the selected profile with the neutral graphite step, not the brand', () => {
    const { model } = privacyModel('plan')
    render(<ApprovalRegister model={model} />)
    const selected = screen.getByTestId('security-profile-plan')
    expect(selected.className).toContain('bg-surface-interactive')
    expect(selected.className).not.toContain('bg-brand')
  })

  it('marks the stored profile as the checked one', () => {
    const { model } = privacyModel('plan')
    render(<ApprovalRegister model={model} />)
    expect(screen.getByTestId('security-profile-plan').getAttribute('aria-checked')).toBe('true')
    expect(screen.getByTestId('security-profile-strict').getAttribute('aria-checked')).toBe('false')
  })

  it('states which surface decides and which one is the ceiling', () => {
    const { model } = privacyModel('strict')
    render(<ApprovalRegister model={model} />)
    const note = screen.getByTestId('privacy-profile-note')
    expect(note.textContent).toContain('composer mode')
    expect(note.textContent).toContain('ceiling')
  })
})
