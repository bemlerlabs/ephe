// WS-E 47 — the panel's empty state, the surface every last-close falls back to.
// One open-card per tab key with its label, each card a real button that opens
// its page, and the focus hand-off that keeps the keyboard walk alive.
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PanelEmptyState } from './panelEmptyState'
import { TAB_KEYS, Tab } from './primitives'

vi.mock('@/lib/api', () => ({
  getSettings: vi.fn(async () => ({ workspace_dir: null })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const labels = Object.fromEntries(TAB_KEYS.map((k) => [k, `L:${k}`])) as Record<Tab, string>

describe('PanelEmptyState', () => {
  it('names the prompt from the locales', () => {
    render(<PanelEmptyState labels={labels} onOpenTab={vi.fn()} />)
    expect(screen.getByTestId('panel-empty-state')).toBeInTheDocument()
    expect(screen.getByText('agentPanel.openTabTitle')).toBeInTheDocument()
    expect(screen.getByText('agentPanel.openTabHint')).toBeInTheDocument()
  })

  it('offers one labelled open-card per tab key', () => {
    render(<PanelEmptyState labels={labels} onOpenTab={vi.fn()} />)
    expect(screen.getAllByTestId(/^panel-tab-card-/)).toHaveLength(TAB_KEYS.length)
    for (const key of TAB_KEYS) {
      expect(screen.getByText(`L:${key}`)).toBeInTheDocument()
    }
  })

  it('cards are real buttons, so Tab reaches them', () => {
    render(<PanelEmptyState labels={labels} onOpenTab={vi.fn()} />)
    for (const key of TAB_KEYS) {
      const card = screen.getByTestId(`panel-tab-card-${key}`)
      expect(card.tagName).toBe('BUTTON')
      expect(card).toHaveAttribute('type', 'button')
    }
  })

  it('opens the page the card names', () => {
    const onOpenTab = vi.fn()
    render(<PanelEmptyState labels={labels} onOpenTab={onOpenTab} />)
    fireEvent.click(screen.getByTestId('panel-tab-card-terminal'))
    expect(onOpenTab).toHaveBeenCalledWith('terminal')
    fireEvent.click(screen.getByTestId('panel-tab-card-side'))
    expect(onOpenTab).toHaveBeenLastCalledWith('side')
  })

  it('takes focus on the first card when the last close dropped it on <body>', () => {
    render(<PanelEmptyState labels={labels} onOpenTab={vi.fn()} />)
    expect(document.activeElement).toBe(screen.getByTestId('panel-tab-card-preview'))
  })

  it('leaves focus alone when the pane still holds it', () => {
    const holder = document.createElement('button')
    document.body.appendChild(holder)
    holder.focus()
    try {
      render(<PanelEmptyState labels={labels} onOpenTab={vi.fn()} />)
      expect(document.activeElement).toBe(holder)
    } finally {
      holder.remove()
    }
  })
})
