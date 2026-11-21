// R3 — the catalog row states what the gate would do, and the switch beside it is
// the same decision the guard reads.
//
// The badge is the whole point: a reader must be able to tell at a glance whether
// a call runs without a prompt. `safe` arrives from the server, so this test pins
// that the row renders the verdict it was handed, not one it guessed. The switch
// pins the other half: off goes to the server that refuses the call, and a locked
// row offers no switch at all.
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const capabilities = vi.fn(async () => ({
  subagent: {
    tools: ['read_file', 'list_directory'],
    tool_count: 2,
    max_iterations: 1,
    read_only: true,
    base_tools: ['read_file'],
    extra_tools: ['list_directory'],
  },
  main_agent: { read_only: false, note: '' },
  tools: {
    count: 3,
    safe_count: 2,
    enabled_count: 3,
    tools: [
      { name: 'read_file', description: 'Read a file', safe: true, enabled: true },
      { name: 'delete_file', description: 'Delete a file', safe: false, enabled: true },
      { name: 'session_search', description: 'Old sessions', safe: true, enabled: true },
      { name: 'ask_user', description: 'Pause', safe: false, enabled: true, locked: true },
    ],
  },
}))

const setCapability = vi.fn(async (name: string, enabled: boolean) => ({ name, enabled }))
const setSubagentAllowlist = vi.fn(async (names: string[]) => ({
  extra_tools: names,
  tools: ['read_file', ...names],
}))

vi.mock('@/lib/api', () => ({
  getCapabilities: () => capabilities(),
  setCapability: (name: string, enabled: boolean) => setCapability(name, enabled),
  setSubagentAllowlist: (names: string[]) => setSubagentAllowlist(names),
}))

import { ToolCatalog } from './ToolCatalog'

describe('ToolCatalog', () => {
  beforeEach(() => {
    setCapability.mockClear()
    setSubagentAllowlist.mockClear()
  })

  it('renders one row per tool with the verdict it was given', async () => {
    render(<ToolCatalog />)

    const safeRow = await screen.findByTestId('tool-row-read_file')
    expect(safeRow.getAttribute('data-safe')).toBe('true')
    expect(safeRow.textContent).toContain('tools.catalogSafe')

    const gatedRow = screen.getByTestId('tool-row-delete_file')
    expect(gatedRow.getAttribute('data-safe')).toBe('false')
    expect(gatedRow.textContent).toContain('tools.catalogAsks')
  })

  it('renders nothing when the server sends no catalog', async () => {
    capabilities.mockResolvedValueOnce({
      subagent: {
        tools: [],
        tool_count: 0,
        max_iterations: 1,
        read_only: true,
        base_tools: [],
        extra_tools: [],
      },
      main_agent: { read_only: false, note: '' },
      tools: { tools: [], count: 0, safe_count: 0, enabled_count: 0 },
    })
    render(<ToolCatalog />)
    await Promise.resolve()
    expect(screen.queryByTestId('tools-catalog')).toBeNull()
  })

  it('sends the flipped state and shows the row as off', async () => {
    render(<ToolCatalog />)

    const toggle = await screen.findByTestId('tool-switch-delete_file')
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    fireEvent.click(toggle)

    await waitFor(() => expect(setCapability).toHaveBeenCalledWith('delete_file', false))
    expect(screen.getByTestId('tool-row-delete_file').getAttribute('data-enabled')).toBe('false')
  })

  it('keeps a locked tool switched on and offers no switch', async () => {
    render(<ToolCatalog />)
    await screen.findByTestId('tool-row-ask_user')
    expect(screen.queryByTestId('tool-switch-ask_user')).toBeNull()
    expect(screen.getByTestId('tool-lock-ask_user')).toBeTruthy()
  })

  it('takes back an own allow-list entry and leaves the stock one in place', async () => {
    render(<ToolCatalog />)

    await screen.findByTestId('allow-chip-read_file')
    expect(screen.queryByTestId('allow-remove-read_file')).toBeNull()
    fireEvent.click(screen.getByTestId('allow-remove-list_directory'))

    await waitFor(() => expect(setSubagentAllowlist).toHaveBeenCalledWith([]))
    await waitFor(() => expect(screen.queryByTestId('allow-chip-list_directory')).toBeNull())
    expect(screen.getByTestId('allow-chip-read_file')).toBeTruthy()
  })
})
