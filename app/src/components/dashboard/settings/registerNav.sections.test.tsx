/**
 * The nav's second level: the tab you are in lists its own sections, and a
 * click lands the page on that section. The list comes from SECTION_TAB, so a
 * tab without sections stays a single row.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RegisterNav } from './registerNav'
import type { DeepSection } from '@/types'
import type { SettingsModel } from './model/buildModel'

const t = ((key: string) => key) as SettingsModel['t']
const none = [] as never[]

function nav(activeTab: 'appearance' | 'cron', sections: DeepSection[]) {
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

describe('settings nav sections', () => {
  it('lists the active tab sections and jumps to the one clicked', () => {
    const onJump = nav('appearance', [
      { key: 'appearance' } as DeepSection,
      { key: 'chat' } as DeepSection,
    ])

    const row = screen.getByTestId('settings-nav-part-appearance-deep-section-appearance')
    expect(row).toBeTruthy()
    // `chat` belongs to the behaviour tab, not this one.
    expect(screen.queryByTestId('settings-nav-part-appearance-deep-section-chat')).toBeNull()

    fireEvent.click(row)
    expect(onJump).toHaveBeenCalledWith('appearance', 'deep-section-appearance')
  })

  it('keeps a tab with neither sections nor parts a single row', () => {
    nav('cron', [{ key: 'appearance' } as DeepSection])
    expect(screen.queryByTestId('settings-nav-sections-cron')).toBeNull()
  })
})
