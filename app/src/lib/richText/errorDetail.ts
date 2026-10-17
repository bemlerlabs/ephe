/**
 * One readable line out of whatever a renderer threw.
 *
 * Mermaid rejects with a multi-line report ("Parse error on line 2: …" followed by
 * a caret line and the token list it expected). Passed through unchanged it fills
 * the bubble with a wall of text and buries the sentence above it.
 */
const MAX_DETAIL = 240

export function errorDetail(err: unknown): string {
  const thrown = err as { str?: unknown } | null
  const raw =
    err instanceof Error
      ? err.message
      : typeof err === 'string'
        ? err
        : typeof thrown?.str === 'string'
          ? thrown.str
          : ''
  const line = raw.replace(/\s+/g, ' ').trim()
  return line.length > MAX_DETAIL ? `${line.slice(0, MAX_DETAIL - 1)}…` : line
}
