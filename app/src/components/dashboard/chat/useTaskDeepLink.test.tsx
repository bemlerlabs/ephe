/**
 * R4 (A3) — the way back out of the workbench.
 *
 * `?session=` restores the session, `?replay=1` opens the replay tab,
 * and both parameters are gone once done: a reload must not redirect
 * again.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { useTaskDeepLink } from './useTaskDeepLink'

const h = vi.hoisted(() => ({ setActiveSession: vi.fn() }))
const seen = vi.hoisted(() => vi.fn())

vi.mock('../AgentPanel', () => ({ PREVIEW_OPEN_EVENT: 'ephe:preview-open' }))
vi.mock('@/store/chatStore', () => ({
  useChatStore: {
    getState: () => ({ activeSessionId: 'andere-sitzung', setActiveSession: h.setActiveSession }),
  },
}))

function Hanger() {
  useTaskDeepLink()
  return null
}
function Ort() {
  const loc = useLocation()
  return <div data-testid="ort" data-search={loc.search} data-pathname={loc.pathname} />
}

const show = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Hanger />
      <Ort />
    </MemoryRouter>,
  )

describe('useTaskDeepLink', () => {
  beforeEach(() => {
    h.setActiveSession.mockClear()
    seen.mockClear()
    window.addEventListener('ephe:preview-open', seen)
    return () => window.removeEventListener('ephe:preview-open', seen)
  })

  it('stellt die Sitzung her, öffnet den Replay und räumt die Parameter ab', () => {
    show('/chat?session=s7&replay=1')
    expect(h.setActiveSession).toHaveBeenCalledWith('s7')
    expect(seen).toHaveBeenCalledTimes(1)
    const event = seen.mock.calls[0]?.[0] as CustomEvent<{ tab?: string }> | undefined
    expect(event?.detail?.tab).toBe('trajectory')
    expect(screen.getByTestId('ort').getAttribute('data-search')).toBe('')
  })

  it('lässt eine bereits offene Sitzung in Ruhe', () => {
    h.setActiveSession.mockImplementation(() => {})
    show('/chat?session=andere-sitzung')
    expect(h.setActiveSession).not.toHaveBeenCalled()
    expect(seen).not.toHaveBeenCalled()
  })

  it('ohne Parameter geschieht nichts', () => {
    show('/chat')
    expect(h.setActiveSession).not.toHaveBeenCalled()
    expect(seen).not.toHaveBeenCalled()
    expect(screen.getByTestId('ort').getAttribute('data-pathname')).toBe('/chat')
  })
})
