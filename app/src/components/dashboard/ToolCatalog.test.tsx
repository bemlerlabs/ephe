// R3 — the catalog row states what the gate would do.
//
// The badge is the whole point: a reader must be able to tell at a glance whether
// a call runs without a prompt. `safe` arrives from the server, so this test pins
// that the row renders the verdict it was handed, not one it guessed.
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const capabilities = vi.fn(async () => ({
  subagent: { tools: [], tool_count: 0, max_iterations: 1, read_only: true },
  main_agent: { read_only: false, note: '' },
  tools: {
    count: 2,
    safe_count: 1,
    tools: [
      { name: 'read_file', description: 'Read a file', safe: true },
      { name: 'delete_file', description: 'Delete a file', safe: false },
    ],
  },
}))

vi.mock('@/lib/api', () => ({
  getCapabilities: () => capabilities(),
}))

import { ToolCatalog } from './ToolCatalog'

describe('ToolCatalog', () => {
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
      subagent: { tools: [], tool_count: 0, max_iterations: 1, read_only: true },
      main_agent: { read_only: false, note: '' },
      tools: { tools: [], count: 0, safe_count: 0 },
    })
    render(<ToolCatalog />)
    await Promise.resolve()
    expect(screen.queryByTestId('tools-catalog')).toBeNull()
  })
})
