'use client'

import { type AuditEntry } from '@/lib/api'
import { fmtClock } from '@/lib/format'
import { intlLocale } from '@/lib/dateLocale'

/** The shapes of an evidence row, on their own: time basis, day group, kind,
 *  duration, signature, error code. All pure functions — no state, no fetch. */

/** The surface's page size — the row below names the total count next to it. */
export const AUDIT_PAGE_LIMIT = 80

/** The kinds the kernel actually writes (core/tools/*, server/routes/*,
 * core/memory_mcp_server, core/channels/*). The filter is complete when it follows
 * the schema — not just whatever the current log happens to contain. */
export const AUDIT_KINDS = [
  'hook',
  'tool_exec',
  'approval',
  'turn',
  'shell',
  'mcp_memory',
  'plugin_gate',
  'channel',
] as const

/** hook → auditKindHook, mcp_memory → auditKindMcpMemory. */
export function auditKindLabelKey(kind: string): string {
  const caps = kind
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')
  return `agentPanel.auditKind${caps}`
}

/** Known kinds in the user's language, unknown ones as their identifier — the same
 * rule as in the hooks area: a name nobody set is never invented here. */
export function auditKindName(kind: string, t: (key: string) => string): string {
  return (AUDIT_KINDS as readonly string[]).includes(kind) ? t(auditKindLabelKey(kind)) : kind
}

/** A number in the surface's language; one decimal place, never an invented value.
 *  `intlLocale` always hands Intl a tag it accepts, so there is no catch left and
 *  with it no last-ditch question to the machine — which is what made a German Mac
 *  print „1.2" inside an English interface. */
export function auditNumber(value: number, lang: string): string {
  return new Intl.NumberFormat(intlLocale(lang), { maximumFractionDigits: 1 }).format(value)
}

/**
 * Duration per call, in the surface's language; null = never measured (no text).
 * ONE path through Intl for both branches — otherwise "1,2 s" (comma) would sit
 * above "942.6 ms" (dot) in a single column, because only the seconds branch
 * had been localised.
 */
export function auditDuration(ms: number | null | undefined, lang: string): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms)) return ''
  const inSeconds = Math.abs(ms) >= 1000
  return `${auditNumber(inSeconds ? ms / 1000 : ms, lang)} ${inSeconds ? 's' : 'ms'}`
}

/** Short form of the argument signature: same short form == same call. */
export function auditSignature(hash: string | undefined): string {
  return hash ? `#${hash.slice(0, 8)}` : ''
}

/** The row's clock time in the same local time as the trajectory and the side chat
 * (fmtClock) — the raw UTC from the log is not. '' when unreadable. */
export function auditClock(ts: string): string {
  const ms = Date.parse(ts)
  return Number.isNaN(ms) ? '' : fmtClock(ms / 1000)
}

/** The machine's zone abbreviation ("MESZ"), so the head of the list states what
 * it is sorted by. '' when the environment names no zone. */
export function auditZoneLabel(lang: string): string {
  const opts: Intl.DateTimeFormatOptions = { hour: '2-digit', timeZoneName: 'short' }
  const parts = new Intl.DateTimeFormat(intlLocale(lang), opts).formatToParts(new Date())
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? ''
}

/** The local calendar day as the group key (YYYY-MM-DD) — the list spans days,
 * and without a group the clock appears to jump backwards. */
export function auditDayKey(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Day heading, in the surface's language („Mo., 05. Okt. 2026"). */
export function auditDayLabel(key: string, lang: string): string {
  if (!key) return ''
  const d = new Date(`${key}T12:00:00`) // noon: DST shifts the clock, never the day
  if (Number.isNaN(d.getTime())) return key
  const opts: Intl.DateTimeFormatOptions = {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }
  return new Intl.DateTimeFormat(intlLocale(lang), opts).format(d)
}

/** request() throws "API <code>: <text>" when the body was not JSON (e.g. a 500
 *  as plain text). That is the status evidence the client can still deliver. */
export function auditErrorCode(message: string): string {
  const m = /^API (\d{3})\b/.exec(message ?? '')
  return m?.[1] ?? ''
}

/** The shape GET /api/audit answers with, once total_matching travels along. */
export type AuditPayload = { entries?: AuditEntry[] | null; total_matching?: number | null }
