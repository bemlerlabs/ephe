import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/lib/tauriBridge', () => ({ isDesktopShell: () => true }))

import { ShortcutsSection } from './sections-shortcuts'
import type { SettingsModel } from './types'

const model = {
  t: (k: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? k,
  i18n: { language: 'en' },
  deepDraft: { shortcuts: { 'shortcuts.global_enabled': false } },
  deepSections: [
    {
      key: 'shortcuts',
      fields: [
        {
          key: 'shortcuts.global_enabled',
          type: 'bool',
          value: false,
          default: false,
          label: 'Globales Kürzel (Desktop)',
          labelEn: 'Global shortcut (desktop)',
          hint: 'Der einzige Schalter …',
          hintEn: 'The one switch …',
        },
      ],
    },
  ],
  setDeepField: vi.fn(),
} as unknown as SettingsModel

describe('ShortcutsSection on the desktop shell', () => {
  it('carries the one saveable global opt-in above the read board', () => {
    render(<ShortcutsSection model={model} />)
    expect(screen.getByTestId('deep-row-shortcuts.global_enabled')).toBeTruthy()
    expect(screen.getByRole('switch')).toBeTruthy()
  })
})
