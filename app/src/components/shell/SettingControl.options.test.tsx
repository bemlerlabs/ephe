/**
 * LS-2: an option reads its text from its leaf, and the register's label is the fallback.
 *
 * Two halves, because `optionKeys` came in additive: the leaf has to win where the register
 * copy is loaded, and a field without keys — or a leaf that never arrived — has to keep
 * painting the label the register sent. A select showing `settings.fooOption13` to a user is
 * the defect this file keeps out. The label fields carry a marker of their own so the leaf
 * case cannot pass by the two texts happening to agree.
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'

import SettingControl from './SettingControl'
import { ensureSettingsCopy } from '@/lib/settingsCopy'
import { default as i18n } from '@/i18n'
import type { DeepField } from '@/types'

const MARKER = 'REGISTER LABEL SLOT'

const base: DeepField = {
  key: 'appearance.base_font_px',
  type: 'select',
  label: 'Basistextgroesse (px)',
  labelEn: 'Base text size (px)',
  default: '13',
  value: '13',
  options: ['13', '14'],
  optionLabels: [
    { value: '13', label: MARKER, labelEn: MARKER },
    { value: '14', label: 'Mittel (14 px)', labelEn: 'Medium (14 px)' },
  ],
}

function renderControl(field: DeepField, value: string) {
  render(<SettingControl field={field} value={value} label={field.label} onCommit={() => {}} />)
}

describe('the option text of a select', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('de')
    await ensureSettingsCopy('de')
  })

  it('reads the leaf the register named', () => {
    renderControl(
      {
        ...base,
        optionKeys: [
          { value: '13', key: 'settings.appearanceBaseFontPxOption13' },
          { value: '14', key: 'settings.appearanceBaseFontPxOption14' },
        ],
      },
      '13',
    )
    expect(screen.getByRole('option', { name: 'Klein (13 px)' })).toBeInTheDocument()
    expect(screen.queryByText(MARKER)).not.toBeInTheDocument()
    expect(screen.queryByText('settings.appearanceBaseFontPxOption13')).not.toBeInTheDocument()
  })

  it('paints the register label when no key came along', () => {
    renderControl({ ...base }, '13')
    expect(screen.getByRole('option', { name: MARKER })).toBeInTheDocument()
  })

  it('falls back to the label when the leaf is not in memory', () => {
    renderControl({ ...base, optionKeys: [{ value: '13', key: 'settings.noSuchLeafAtAll' }] }, '13')
    expect(screen.getByRole('option', { name: MARKER })).toBeInTheDocument()
    expect(screen.queryByText('settings.noSuchLeafAtAll')).not.toBeInTheDocument()
  })
})
