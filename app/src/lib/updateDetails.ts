/**
 * What the shell reports about the package it is installing.
 *
 * The dialog shows the facts the update carried. The release notes come from
 * the feed, the download size from the transfer itself, and the package name
 * from the manifest the updater resolved. A value the source did not report
 * stays undefined, so the surface can say it was not reported.
 */

const KNOWN_SIZE_UNITS = ['B', 'kB', 'MB', 'GB'] as const

/** Bytes in the unit a person reads. `undefined` in, `undefined` out. */
export function formatBytes(bytes: number | undefined): string | undefined {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes <= 0) return undefined
  let value = bytes
  let unit = 0
  while (value >= 1000 && unit < KNOWN_SIZE_UNITS.length - 1) {
    value /= 1000
    unit += 1
  }
  const rounded = value >= 10 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10
  return `${rounded} ${KNOWN_SIZE_UNITS[unit]}`
}

/** The file name the updater resolved for this platform, without query or host. */
export function readAsset(rawJson: unknown): string | undefined {
  if (!rawJson || typeof rawJson !== 'object') return undefined
  const url = (rawJson as Record<string, unknown>).url
  if (typeof url !== 'string' || !url) return undefined
  const tail = url.split('/').pop()
  if (!tail) return undefined
  const name = tail.split('?')[0]
  return name || undefined
}

/** The host platform the shell runs on. */
export function readPlatform(): string | undefined {
  if (typeof navigator === 'undefined') return undefined
  return navigator.platform || undefined
}

/** The notes the updater manifest carried, when the feed held none. */
export function readManifestNotes(body: unknown): string | undefined {
  return typeof body === 'string' && body.trim().length > 0 ? body : undefined
}
