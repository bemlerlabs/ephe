/**
 * Ephe — thinking duration labels (PWA-Chat-UX-Plan, Task A2)
 *
 * Pure helper — no i18n import (testable without i18n initialisation):
 * the caller passes in the `t` function of react-i18next.
 */

/** Below this threshold the collapsed block shows the "kurz nachgedacht" label instead of a seconds count — language-gate: ignore (quotes the German locale value rendered by chat.thoughtBriefly) */
export const THRESHOLD_MS = 3000

/** Cap on Thinking.text in the store (tail-trim once it is exceeded) */
export const THINKING_MAX_CHARS = 60_000

/**
 * Compact duration wording: 4000 → "4s", 65000 → "1m 5s",
 * 359000 → "5m 59s" (finest granularity: one second).
 */
export function formatDurationShort(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

type Translator = (key: string, opts?: Record<string, unknown>) => string

/**
 * Label of the collapsed thinking block:
 * - below 3s  → "Kurz nachgedacht" (chat.thoughtBriefly) // language-gate: ignore — quotes the German locale value the product renders
 * - 3s and up → "Gedacht für 4s" (chat.thoughtForSeconds, {{duration}}) // language-gate: ignore — quotes the German locale value the product renders
 */
export function formatThinkingLabel(ms: number, t: Translator): string {
  if (ms < THRESHOLD_MS) return t('chat.thoughtBriefly')
  return t('chat.thoughtForSeconds', { duration: formatDurationShort(ms) })
}
