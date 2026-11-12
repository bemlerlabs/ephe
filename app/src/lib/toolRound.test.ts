/**
 * Wave 3 (web intake): the research row opens itself.
 *
 * The cards are what the reader came for; the tool's own text stays one
 * disclosure down. Every other web tool keeps its closed row.
 */
import { describe, it, expect } from 'vitest'
import { shouldAutoOpen } from './toolRound'
import type { ToolCall } from '@/store/chatStore'

const call = (over: Partial<ToolCall>): ToolCall => ({
  id: 'call-1',
  name: 'web_research',
  args: { query: 'moon drift' },
  result: '[web_research] query="moon drift"',
  status: 'completed',
  ...over,
})

describe('shouldAutoOpen', () => {
  it('opens a finished research call', () => {
    expect(shouldAutoOpen(call({}))).toBe(true)
  })

  it('keeps a running research call closed', () => {
    expect(shouldAutoOpen(call({ status: 'pending' }))).toBe(false)
  })

  it('does not open an ordinary web search', () => {
    expect(shouldAutoOpen(call({ name: 'web_search' }))).toBe(false)
  })
})
