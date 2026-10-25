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
    reason_params: { status: '404' },
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
    expect(screen.getByText('fetch_url failed')).toBeInTheDocument()
    expect(screen.getByTestId('tool-failure-reason').textContent).toBe(
      'The page answered HTTP 404.',
    )
    expect(screen.queryByText('fetch_url completed')).not.toBeInTheDocument()
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

    expect(screen.getByText('fetch_url fehlgeschlagen')).toBeInTheDocument()
    expect(screen.getByTestId('tool-failure-reason').textContent).toBe(
      'Die Seite antwortet mit HTTP 404.',
    )
  })
})
