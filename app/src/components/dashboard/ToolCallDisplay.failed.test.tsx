/**
 * S21: a tool call that failed says so and names its reason.
 *
 * GIVEN  a tool_done frame the backend marked failed (a fetch with an HTTP error)
 * WHEN   the card renders
 * THEN   it shows Failed plus the translated reason, never Completed, and the
 *        family hint lives in the body instead of a hover overlay.
 */
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import i18n from '@/i18n'
import de from '@/locales/de.json'
import ToolCallDisplay from './ToolCallDisplay'
import type { ToolCall } from '@/store/chatStore'

function failedFetch(): ToolCall {
  return {
    id: 'fetch-1',
    name: 'fetch_url',
    args: { url: 'https://example.test/missing', prompt: 'summarize' },
    result: '[fetch failed] HTTP 404 for https://example.test/missing',
    status: 'failed',
    reason_code: 'fetch_http_error',
    reason_params: { status: '404', url: 'https://example.test/missing' },
  }
}

afterEach(cleanup)

describe('ToolCallDisplay — failed call', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('shows Failed and the translated reason for the code', () => {
    render(<ToolCallDisplay tool_calls={[failedFetch()]} />)

    expect(screen.getByTestId('tool-card')).toHaveAttribute('data-status', 'failed')
    // UI-CHAT: name once, outcome once — the old "name + failed" suffix is gone.
    expect(screen.getAllByText('fetch_url')).toHaveLength(1)
    expect(screen.getByTestId('tool-outcome').textContent).toContain('Failed')
    expect(screen.getByTestId('tool-failure-reason').textContent).toBe(
      '[fetch failed] https://example.test/missing answered HTTP 404.',
    )
    expect(screen.queryByText(/completed/i)).not.toBeInTheDocument()
  })

  it('falls back to the result line when the code has no entry', () => {
    const tool = { ...failedFetch(), reason_code: undefined, reason_params: undefined }

    render(<ToolCallDisplay tool_calls={[tool]} />)

    expect(screen.getByTestId('tool-failure-reason').textContent).toBe(
      'HTTP 404 for https://example.test/missing',
    )
  })

  it('keeps the family hint inside the card', () => {
    render(<ToolCallDisplay tool_calls={[failedFetch()]} />)

    expect(screen.getByTestId('tool-card-hint')).toBeInTheDocument()
  })
})

describe('ToolCallDisplay — failed call in German', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('de')
  })

  it('translates the status and the reason', () => {
    render(<ToolCallDisplay tool_calls={[failedFetch()]} />)

    const reason = de.reader.fetch_http_error
      .replace('{{url}}', 'https://example.test/missing')
      .replace('{{status}}', '404')

    expect(screen.getAllByText('fetch_url')).toHaveLength(1)
    expect(screen.getByTestId('tool-outcome').textContent).toContain(de.chat.rowFailed)
    expect(screen.getByTestId('tool-failure-reason').textContent).toBe(reason)
  })
})
