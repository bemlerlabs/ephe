/**
 * The nav's third step: an area lists the blocks its page is built from, and a
 * sub-row lands the column on that block. Two sources feed one list — the register
 * blocks the server sends and the page blocks the section modules render by hand —
 * so an area with no schema section still expands.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RegisterNav } from './registerNav'
import type { DeepSection } from '@/types'
import type { SettingsModel } from './model/buildModel'

const t = ((key: string) => key) as SettingsModel['t']
const none = [] as never[]

function nav(activeTab: Parameters<typeof RegisterNav>[0]['activeTab'], sections: DeepSection[]) {
  const onJump = vi.fn()
  render(
    <RegisterNav
      query=""
      tabHits={none}
      fieldHits={none}
      rowHits={none}
      activeTab={activeTab}
      sections={sections}
      t={t}
      onJump={onJump}
      onSelect={vi.fn()}
    />,
  )
  return onJump
}

describe('settings nav page parts', () => {
  it('expands an area that has no register block', () => {
    const onJump = nav('network', [])
    const row = screen.getByTestId('settings-nav-part-network-network-group-server')
    expect(row.textContent).toBe('settings.networkGroupServer')

    fireEvent.click(row)
    expect(onJump).toHaveBeenCalledWith('network', 'network-group-server')
  })

  it('keeps the register block between the page blocks that surround it', () => {
    nav('appearance', [{ key: 'appearance' } as DeepSection])
    const rows = screen
      .getAllByTestId(/settings-nav-part-appearance-/)
      .map((node) => node.getAttribute('data-testid')?.replace('settings-nav-part-appearance-', ''))
    expect(rows).toEqual([
      'appearance-presets',
      'companion-studio',
      'deep-section-appearance',
      'appearance-profile-group',
    ])
  })

  it('drops the register block when the server sends no fields for it', () => {
    nav('appearance', [])
    expect(screen.queryByTestId('settings-nav-part-appearance-deep-section-appearance')).toBeNull()
    expect(screen.getByTestId('settings-nav-part-appearance-appearance-presets')).toBeTruthy()
  })
})
