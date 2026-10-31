/**
 * How a catalogue row is called: the launch-line name, the publisher namespace,
 * the human-readable title, and the shelf's subject order. Split from the
 * mapping so neither file owns the other's work.
 */

/**
 * The stable name of a launch line. A remote endpoint keeps its host and path
 * (`mcp.linear.app/mcp`) — the bare last segment would collapse every `/mcp`
 * server into one row. A stdio line names itself after the package, so
 * `npx:weather` and `stdio:npx -y @scope/weather@1` both read `weather`.
 */
export const specName = (spec: string): string => {
  const trimmed = spec.trim()
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const url = new URL(trimmed)
      return `${url.host}${url.pathname}`.replace(/\/+$/, '')
    } catch {
      return trimmed
    }
  }
  const body = trimmed.startsWith('stdio:') ? trimmed.slice('stdio:'.length).trim() : trimmed
  const tail = body.includes(':') ? body.slice(body.lastIndexOf(':') + 1) : body
  const head = tail.startsWith('stdio:') ? tail.slice('stdio:'.length) : tail
  const command = head.split(/\s+/).filter((part) => !part.startsWith('-'))
  const named = command.find((part) => !/^(npx|bunx|uvx|uv|run|python3?|node|deno)$/.test(part))
  if (!named) return body
  const bare = named.replace(/^@/, '').split('@')[0] ?? ''
  const parts = bare.split('/')
  const leaf = parts.pop() ?? ''
  // `@playwright/mcp` would otherwise collapse to "mcp", which other scopes use too.
  const generic = /^(mcp|server|cli|sdk|api)$/i.test(leaf) && parts.length > 0
  return (generic ? `${parts.pop()}/${leaf}` : leaf) || bare || body
}

/** The shelf's own order: the subjects a person browses, ahead of the alphabet. */
export const CATEGORY_ORDER = [
  'skills',
  'code',
  'web',
  'memory',
  'files',
  'communication',
  'productivity',
  'database',
  'cloud',
  'security',
  'media',
  'utility',
  'testing',
  'sandbox',
  'other',
] as const

/** `com.ainetcafe/netcafe-memory` reads as "Netcafe Memory" on a card. */
export function prettyName(name: string): string {
  if (!name) return name
  const tail = name.includes('/') ? name.slice(name.lastIndexOf('/') + 1) : name
  if (!tail) return name
  // A name that already carries spaces and capitals was written for people.
  if (/\s/.test(tail) && /[A-Z]/.test(tail)) return tail
  return tail
    .replace(/[._-]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .map((word) =>
      /^(ai|api|cli|mcp|sdk|db|ui|css|json|http|sql)$/i.test(word)
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1),
    )
    .join(' ')
}

/** The namespace before the slash names who published the entry. */
export function publisherOf(name: string): string | undefined {
  if (!name.includes('/')) return undefined
  const head = name.slice(0, name.lastIndexOf('/'))
  return head || undefined
}

/**
 * A publisher launch line becomes the config spec the connector rides on.
 * Remote hints ride on their URL; a command line is prefixed with `stdio:`.
 * A trailing parenthetical (`(stdio)`, `(streamable-http, OAuth)`) is an
 * annotation, not part of the command. A hint that still carries a `<folder>`
 * placeholder asks for an argument the catalogue cannot invent — it returns
 * null so the page says so instead of writing a line that cannot start.
 */
export function registrySpec(hint: string): string | null {
  const trimmed = hint.trim()
  const url = trimmed.match(/^https?:\/\/[^\s)]+/i)?.[0]
  if (url) return url
  const command = trimmed.replace(/\s*\([^)]*\)\s*$/, '').trim()
  if (!command || /<[^>]+>/.test(command)) return null
  if (!/^(npx|bunx|uvx|uv run|python3?|node|deno)\s+\S+/.test(command)) return null
  return `stdio:${command}`
}
