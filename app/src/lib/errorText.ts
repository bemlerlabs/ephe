const KNOWN: Array<[RegExp, string]> = [
  [
    /(econnrefused|connection refused|failed to connect|fetch failed|ollama.*not reachable|not reachable|connecte? econn)/i,
    'chat.errorEngineUnreachable',
  ],
  [/(401|403|unauthorized|invalid api key|refused the key|key rejected)/i, 'chat.errorEngineKey'],
  [/(timeout|timed out|etimedout)/i, 'chat.errorEngineTimeout'],
]

/**
 * Translates a known connection failure into the UI language.
 *
 * The backend's sentence is precise and in English; a user whose app runs in German
 * should not meet that sentence in a red box. An unknown error keeps its text — a
 * translation would be a guess about what failed.
 */
export function friendlyError(raw: string, t: (key: string) => string): string {
  for (const [pattern, key] of KNOWN) {
    if (pattern.test(raw)) return t(key)
  }
  return raw
}
