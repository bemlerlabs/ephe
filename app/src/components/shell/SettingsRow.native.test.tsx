import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { DeepField } from '@/types'
import SettingControl from './SettingControl'
import { SettingsGroup, SettingsRow, SettingValue } from './SettingsRow'
import Switch from './Switch'

function numberField(): DeepField {
  return {
    key: 'appearance.font_scale',
    type: 'number',
    label: 'Font scale',
    labelEn: 'Font scale',
    default: 100,
    value: 100,
    min: 80,
    max: 150,
  }
}

describe('settings primitives — native contract', () => {
  it('renders a group as an inset card, not a sticky ruled band', () => {
    render(
      <SettingsGroup title="Everyday" testid="group">
        <SettingsRow title="Font scale" testid="row">
          <SettingValue>100%</SettingValue>
        </SettingsRow>
      </SettingsGroup>,
    )
    const group = screen.getByTestId('group')
    expect(group.querySelector('.rounded-xl')).toBeTruthy()
    expect(group.querySelector('.bg-surface')).toBeTruthy()
    expect(group.querySelector('.sticky')).toBeNull()
  })

  it('keeps a 44 px row floor and a sentence-face value', () => {
    render(
      <SettingsRow title="Font scale" testid="row">
        <SettingValue>100%</SettingValue>
      </SettingsRow>,
    )
    expect(screen.getByTestId('row').className).toContain('min-h-11')
    const value = screen.getByText('100%')
    expect(value.className).not.toContain('font-mono')
    expect(value.className).not.toContain('w-44')
  })

  it('marks a set switch by position and graphite, not brand fill', () => {
    render(<Switch checked onChange={() => {}} label="Animations" testid="switch" />)
    const sw = screen.getByTestId('switch')
    expect(sw.className).toContain('bg-ink')
    expect(sw.className).not.toContain('bg-brand')
  })

  it('gives a number field the native shell', () => {
    render(
      <SettingControl field={numberField()} value={100} label="Font scale" onCommit={() => {}} />,
    )
    const input = screen.getByTestId('setting-number-appearance.font_scale')
    expect(input.className).toContain('rounded-lg')
    expect(input.className).toContain('bg-surface-raised')
    expect(input.className).not.toContain('font-mono')
  })
})
