// I6-5: the shortcuts as a section — a read board made from the single table.
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { ShortcutsSection } from './sections-shortcuts'
import { SHORTCUTS } from '@/lib/shortcuts'
import type { SettingsModel } from './types'

const model = {
  t: (k: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? k,
  i18n: { language: 'de' },
} as unknown as SettingsModel

/** The rows themselves — without the description nodes SettingsRow adds. */
const rowsOf = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('[data-testid^="shortcuts-row-"]')).filter(
    (el) => !el.getAttribute('data-testid')?.endsWith('-desc'),
  )

describe('ShortcutsSection', () => {
  it('lists every shortcut of the table exactly once', () => {
    const { container } = render(<ShortcutsSection model={model} />)
    for (const s of SHORTCUTS) {
      expect(screen.getByTestId(`shortcuts-row-${s.id}`)).toBeTruthy()
    }
    expect(rowsOf(container).length).toBe(SHORTCUTS.length)
  })

  it('groups by navigation, composer and everywhere', () => {
    const { container } = render(<ShortcutsSection model={model} />)
    for (const key of ['navigation', 'composer', 'global']) {
      expect(screen.getByTestId(`shortcuts-group-${key}`)).toBeTruthy()
    }
    // The groups cover the whole table — no entry gets lost.
    expect(rowsOf(container).length).toBe(SHORTCUTS.length)
  })

  it('says honestly that the binding is not changed here', () => {
    render(<ShortcutsSection model={model} />)
    expect(screen.getByTestId('shortcuts-fixed-note').textContent).toContain('shortcutsFixed')
    // no dead button, no field: the board offers no control
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.queryByRole('switch')).toBeNull()
  })
})
