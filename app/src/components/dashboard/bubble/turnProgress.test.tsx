import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TurnProgressLine from './turnProgress'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => `${k}|${JSON.stringify(o ?? {})}` }),
}))

describe('S17: the live progress line', () => {
  it('names the search round, the query and the elapsed time', () => {
    render(
      <TurnProgressLine
        progress={{
          tool: 'web_search',
          round: 2,
          roundCap: 4,
          phase: 'tool_progress',
          elapsedMs: 65_000,
          query: 'dgx spark price',
        }}
      />,
    )
    const label = screen.getByTestId('turn-progress-label').textContent ?? ''
    expect(label).toContain('"time":"1m 5s"')
    expect(label).toContain('"round":2')
    expect(label).toContain('"cap":4')
    expect(label).toContain('dgx spark price')
    expect(screen.getByTestId('turn-progress').textContent).toContain('chat.searchWaiting')
  })

  it('drops the waiting word once the tool answered', () => {
    render(
      <TurnProgressLine
        progress={{
          tool: 'web_search',
          round: 2,
          roundCap: 4,
          phase: 'tool_done',
          elapsedMs: 8000,
          query: 'x',
        }}
      />,
    )
    expect(screen.getByTestId('turn-progress').textContent).not.toContain('chat.searchWaiting')
  })
})
