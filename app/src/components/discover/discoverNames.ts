/**
 * How a catalogue row is called: the launch-line name, the publisher namespace,
 * the human-readable title, and the shelf's subject order. Split from the
 * mapping so neither file owns the other's work.
 */

/** `npx:weather` and `uvx:maps@1` both name themselves after the colon. */
export const specName = (spec: string): string => {
  const tail = spec.includes(':') ? spec.slice(spec.lastIndexOf(':') + 1) : spec
  const head = tail.replace(/^@/, '').split('@')[0] ?? ''
  return head.split('/').pop() || spec
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
