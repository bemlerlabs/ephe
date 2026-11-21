/**
 * The two panes stay out of the boot. Nothing of either chunk renders before the
 * first request that opens it, and the request that triggers the mount still
 * lands on the pane — otherwise the click that opens it would be swallowed by
 * the gate that made the pane lazy.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { DeferredAgentPanel, DeferredSettingsPanel } from './panels'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'

vi.mock('../AgentPanel', () => ({
  default: ({ boot, onReady }: { boot?: { tab?: string } | null; onReady?: () => void }) => {
    // The real pane reports readiness from its mount effect; a microtask keeps
    // the parent update out of the child's render.
    queueMicrotask(() => onReady?.())
    return <div data-testid="agent-pane">{boot?.tab ?? 'none'}</div>
  },
}))

vi.mock('../SettingsPanel', () => ({
  default: ({ isOpen }: { isOpen: boolean }) => (
    <div data-testid="settings-pane" data-open={String(isOpen)} />
  ),
}))

beforeEach(() => {
  localStorage.clear()
})

describe('DeferredAgentPanel', () => {
  it('renders no pane until an open request arrives', () => {
    render(<DeferredAgentPanel messages={[]} />)
    expect(screen.queryByTestId('agent-pane')).toBeNull()
  })

  it('mounts on the first request and hands that request to the pane', async () => {
    render(<DeferredAgentPanel messages={[]} />)
    act(() => {
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'files' } }))
    })
    const pane = await screen.findByTestId('agent-pane')
    expect(pane.textContent).toBe('files')
  })

  it('uses the latest request while the chunk is still loading', async () => {
    render(<DeferredAgentPanel messages={[]} />)
    act(() => {
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'terminal' } }))
      window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'memory' } }))
    })
    const pane = await screen.findByTestId('agent-pane')
    expect(pane.textContent).toBe('memory')
  })
})

describe('DeferredSettingsPanel', () => {
  it('renders nothing while closed and mounts on the first open', async () => {
    const { rerender } = render(<DeferredSettingsPanel isOpen={false} onClose={() => {}} />)
    expect(screen.queryByTestId('settings-pane')).toBeNull()
    rerender(<DeferredSettingsPanel isOpen onClose={() => {}} />)
    expect((await screen.findByTestId('settings-pane')).dataset.open).toBe('true')
  })

  it('keeps the pane mounted after a close so its exit transition can run', async () => {
    const { rerender } = render(<DeferredSettingsPanel isOpen onClose={() => {}} />)
    await screen.findByTestId('settings-pane')
    rerender(<DeferredSettingsPanel isOpen={false} onClose={() => {}} />)
    expect(screen.getByTestId('settings-pane').dataset.open).toBe('false')
  })
})
