import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ToolbarRow from '@/components/dashboard/ToolbarRow'
import { PANEL_STATE_EVENT } from '@/components/dashboard/AgentPanel'
import type { ChatMessage } from '@/types'

// P1 [F4] the toolbar chips behave like menus: ▾ opens a real dropdown holding
// intelligent actions (the last artifacts of the session, adjacent tabs);
// the active panel tab marks its chip. Clicking a chip still jumps to the tab.

const ARTIFACT_MSG: ChatMessage = {
  id: 'a1',
  role: 'assistant',
  content: '',
  timestamp: Date.now(),
  artifacts: [
    {
      id: 'art1',
      artifact_type: 'file',
      content: '',
      language: '',
      title: 'report.pdf',
      filename: 'report.pdf',
    },
    {
      id: 'art2',
      artifact_type: 'file',
      content: '',
      language: '',
      title: 'sketch.png',
      filename: 'sketch.png',
    },
  ],
}

describe('ToolbarRow Chip-Menüs (P1 [F4])', () => {
  it('Chip-Klick springt wie gehabt in den Tab (kein Menü)', () => {
    render(<ToolbarRow />)
    const seen: CustomEvent[] = []
    const catcher = (e: Event) => seen.push(e as CustomEvent)
    window.addEventListener('ephe:preview-open', catcher)
    fireEvent.click(screen.getByTestId('toolbar-git'))
    window.removeEventListener('ephe:preview-open', catcher)
    expect((seen[0]!.detail as { tab?: string }).tab).toBe('git')
    expect(screen.queryByTestId('toolbar-dropdown-git')).toBeNull()
  })

  it('▾ öffnet das Menü; Eintrag dispatcht den benachbarten Tab', async () => {
    render(<ToolbarRow />)
    fireEvent.click(screen.getByTestId('toolbar-terminal-menu'))
    const dropdown = screen.getByTestId('toolbar-dropdown-terminal')
    expect(dropdown).toBeTruthy()
    const seen: CustomEvent[] = []
    const catcher = (e: Event) => seen.push(e as CustomEvent)
    window.addEventListener('ephe:preview-open', catcher)
    try {
      fireEvent.click(screen.getByTestId('toolbar-menu-item-0'))
    } finally {
      window.removeEventListener('ephe:preview-open', catcher)
    }
    expect((seen[0]!.detail as { tab?: string }).tab).toBe('audit')
    // the dropdown closes on its own once the action ran
    await waitFor(() => expect(screen.queryByTestId('toolbar-dropdown-terminal')).toBeNull())
  })

  it('files-Menü listet die letzten Artefakte der Session; Klick öffnet die Preview-URL', () => {
    render(<ToolbarRow messages={[ARTIFACT_MSG]} />)
    fireEvent.click(screen.getByTestId('toolbar-files-menu'))
    // Newest first: within a message the entry created last wins.
    expect(screen.getByTestId('toolbar-menu-item-0').textContent).toContain('sketch.png')
    expect(screen.getByTestId('toolbar-menu-item-1').textContent).toContain('report.pdf')
    const seen: CustomEvent[] = []
    const catcher = (e: Event) => seen.push(e as CustomEvent)
    window.addEventListener('ephe:preview-open', catcher)
    try {
      fireEvent.click(screen.getByTestId('toolbar-menu-item-1'))
    } finally {
      window.removeEventListener('ephe:preview-open', catcher)
    }
    expect(String((seen[0]!.detail as { url?: string }).url)).toContain('report.pdf')
  })

  it('PANEL_STATE_EVENT markiert den aktiven Chip (aria-current)', () => {
    render(<ToolbarRow />)
    expect(screen.getByTestId('toolbar-preview').getAttribute('aria-current')).toBeNull()
    act(() => {
      window.dispatchEvent(
        new CustomEvent(PANEL_STATE_EVENT, { detail: { open: true, tab: 'preview' } }),
      )
    })
    expect(screen.getByTestId('toolbar-preview').getAttribute('aria-current')).toBe('true')
    expect(screen.getByTestId('toolbar-files').getAttribute('aria-current')).toBeNull()
  })

  it('Escape schließt das offene Menü', () => {
    render(<ToolbarRow />)
    fireEvent.click(screen.getByTestId('toolbar-git-menu'))
    expect(screen.getByTestId('toolbar-dropdown-git')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('toolbar-dropdown-git')).toBeNull()
  })
})
