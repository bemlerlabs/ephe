import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import '@/i18n'

const api = vi.hoisted(() => ({ getCapabilities: vi.fn() }))
vi.mock('@/lib/api', () => ({ getCapabilities: api.getCapabilities }))

import { McpSandboxStrip, resetMcpSandboxFacts } from './McpSandboxStrip'

const facts = (over: Record<string, unknown> = {}) => ({
  subagent: { tools: [], tool_count: 9, max_iterations: 8, read_only: true },
  main_agent: { read_only: false, note: '' },
  mcp_sandbox: {
    platform: 'bubblewrap',
    available: true,
    home_root: '/home/u/.ephe/mcp/homes',
    network_isolated: false,
    pid_isolated: true,
    ...over,
  },
})

beforeEach(() => {
  api.getCapabilities.mockReset()
  resetMcpSandboxFacts()
})

describe('the MCP sandbox strip', () => {
  it('states the platform, the file root and which namespaces are shared', async () => {
    api.getCapabilities.mockResolvedValue(facts())
    render(<McpSandboxStrip server="docs" />)
    const strip = await screen.findByTestId('mcp-sandbox-docs')
    expect(strip.textContent).toContain('bubblewrap')
    expect(strip.textContent).toContain('/home/u/.ephe/mcp/homes')
    expect(strip.textContent).toContain('net shared')
    expect(strip.textContent).toContain('pid isolated')
  })

  it('reads a seatbelt host as a shared pid space', async () => {
    api.getCapabilities.mockResolvedValue(facts({ platform: 'seatbelt', pid_isolated: false }))
    render(<McpSandboxStrip server="docs" />)
    const strip = await screen.findByTestId('mcp-sandbox-docs')
    expect(strip.textContent).toContain('seatbelt')
    expect(strip.textContent).toContain('pid shared')
  })

  it('shows nothing when the route cannot answer', async () => {
    api.getCapabilities.mockRejectedValue(new Error('offline'))
    const { container } = render(<McpSandboxStrip server="docs" />)
    await waitFor(() => expect(api.getCapabilities).toHaveBeenCalled())
    expect(container.querySelector('[data-testid="mcp-sandbox-docs"]')).toBeNull()
  })
})
