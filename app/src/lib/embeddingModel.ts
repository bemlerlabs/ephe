/**
 * The embedding model the memory would like and the install does not carry.
 *
 * The weights are ~542 MB, so the product never fetches them unasked. This module
 * reads whether the model is loadable and starts the fetch only because a person
 * pressed the offer's button. Nothing here writes the consent setting: a click is one
 * fetch, and an automatic fetch keeps needing `memory.embedder_allow_download`.
 */
import { request } from '@/lib/api/http'

/** The pass that gives chunks stored before the fetch a vector under the new model. */
export type EmbeddingReembed = {
  running: boolean
  done: boolean
  total: number
  embedded: number
  remaining: number
  label: string
  error: string
}

export type EmbeddingModelStatus = {
  label: string
  present: boolean
  missing: string[]
  sizeMb: number
  host: string
  repo: string
  consent: boolean
  offline: boolean
  downloading: boolean
  downloaded: boolean
  error: string
  /** Counters of the re-embed pass; absent on a backend that predates it. */
  reembed: EmbeddingReembed
}

const NO_REEMBED: EmbeddingReembed = {
  running: false,
  done: false,
  total: 0,
  embedded: 0,
  remaining: 0,
  label: '',
  error: '',
}

function parseReembed(raw: unknown): EmbeddingReembed {
  const value = (raw ?? {}) as Record<string, unknown>
  return {
    running: value.running === true,
    done: value.done === true,
    total: Number(value.total ?? 0),
    embedded: Number(value.embedded ?? 0),
    remaining: Number(value.remaining ?? 0),
    label: String(value.label ?? ''),
    error: String(value.error ?? ''),
  }
}

type RawStatus = Record<string, unknown>

function parse(raw: RawStatus): EmbeddingModelStatus {
  return {
    label: String(raw.label ?? ''),
    present: raw.present === true,
    missing: Array.isArray(raw.missing) ? raw.missing.map(String) : [],
    sizeMb: Number(raw.size_mb ?? 0),
    host: String(raw.host ?? ''),
    repo: String(raw.repo ?? ''),
    consent: raw.consent === true,
    offline: raw.offline === true,
    downloading: raw.downloading === true,
    downloaded: raw.downloaded === true,
    error: String(raw.error ?? ''),
    reembed: raw.reembed ? parseReembed(raw.reembed) : { ...NO_REEMBED },
  }
}

/** The status, or null when the route is unreachable (an older build). */
export async function readEmbeddingModel(): Promise<EmbeddingModelStatus | null> {
  try {
    return parse(await request<RawStatus>('/api/models/embedding'))
  } catch {
    return null
  }
}

/** Start one fetch because the user asked. True when the route accepted it. */
export async function startEmbeddingDownload(): Promise<boolean> {
  try {
    const body = await request<{ started?: boolean }>('/api/models/embedding/download', {
      method: 'POST',
      body: JSON.stringify({ confirm: 'download' }),
    })
    return body.started === true
  } catch {
    return false
  }
}

/** Start one pass over the chunks the active label does not cover. */
export async function startEmbeddingReembed(): Promise<boolean> {
  try {
    const body = await request<{ started?: boolean }>('/api/models/embedding/reembed', {
      method: 'POST',
      body: JSON.stringify({ confirm: 'reembed' }),
    })
    return body.started === true
  } catch {
    return false
  }
}

export const DISMISS_KEY = 'ephe.embeddingModelPrompt.dismissedAt'
/** Ask again after a month: a dismissed offer is not a permanent no. */
export const DISMISS_DAYS = 30

/** Whether the offer was declined recently enough to stay quiet. */
export function recentlyDismissed(now = Date.now()): boolean {
  try {
    const stamp = Number(window.localStorage.getItem(DISMISS_KEY) ?? 0)
    if (!stamp) return false
    return now - stamp < DISMISS_DAYS * 24 * 3600 * 1000
  } catch {
    return false
  }
}

export function dismissOffer(now = Date.now()): void {
  try {
    window.localStorage.setItem(DISMISS_KEY, String(now))
  } catch {
    // A browser without storage still gets the offer; it just comes back next time.
  }
}
