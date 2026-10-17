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

import { renderPrivacy } from './sections-misc'
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
    render(<>{renderPrivacy(model)}</>)
    const radio = screen.getByTestId(`security-profile-${profile}`)
    expect(radio.getAttribute('role')).toBe('radio')
    expect(radio.textContent?.trim().length ?? 0).toBeGreaterThan(0)
  })

  it('hands the chosen profile to the save call', () => {
    const { model, handleSecuritySave } = privacyModel('strict')
    render(<>{renderPrivacy(model)}</>)
    fireEvent.click(screen.getByTestId('security-profile-full'))
    expect(handleSecuritySave).toHaveBeenCalledWith({ approval_profile: 'full' })
  })

  it('marks the stored profile as the checked one', () => {
    const { model } = privacyModel('plan')
    render(<>{renderPrivacy(model)}</>)
    expect(screen.getByTestId('security-profile-plan').getAttribute('aria-checked')).toBe('true')
    expect(screen.getByTestId('security-profile-strict').getAttribute('aria-checked')).toBe('false')
  })

  it('states which surface decides and which one is the ceiling', () => {
    const { model } = privacyModel('strict')
    render(<>{renderPrivacy(model)}</>)
    const note = screen.getByTestId('privacy-profile-note')
    expect(note.textContent).toContain('composer mode')
    expect(note.textContent).toContain('ceiling')
  })
})
