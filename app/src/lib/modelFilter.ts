/**
 * Ephe — model list hygiene (finding 2026-10-01, t5 audit; P3 wave 2026-10-05).
 *
 * Endpoint history and the environment scan contain entries that should never be
 * selectable in the chat: the bare "test" model name and embedding models (they
 * return no chat answers, only vectors). The filter applies to the model chip,
 * the chip menu and the engine model list.
 *
 * P3 (user review run 2026-10-05) adds two duties:
 *  1. Kind separation — speech/image models (whisper-1, dall-e, tts-…) must not
 *     sit between chat models. They are NOT deleted (the scan really found them),
 *     but flagged as their own kind so the list can show them in a section of
 *     their own.
 *  2. Unfilled variables — endpoints like
 *     `https://${SNOWFLAKE_ACCOUNT}.snowflakecomputing.com/…` are catalog
 *     templates without an account value. No request is possible against them; an
 *     entry on one must never be selectable (never silently bind a model to a
 *     template).
 *
 * Everything here is pure classification over the real data (name/endpoint) —
 * no invented fields, no fetch.
 */

/** Model kind — only as far as the NAME really supports. */
export type ModelKind = 'chat' | 'speech' | 'image' | 'embedding' | 'moderation'

/**
 * Models that must never land in the selection system: no answer, only vectors
 * (embeddings), or a bare test entry.
 */
export function isJunkModel(model: string | undefined | null): boolean {
  if (!model) return false
  const m = model.toLowerCase()
  if (m === 'test') return true
  // "embed", "embedding", "nomic-embed-text", "bge-m3" … but NOT
  // "embedded-…" foreign words without model context (word boundaries via non-letters).
  return /(^|[^a-z])embed(ding)?s?([^a-z]|$)/.test(m)
}

/** Speech (ASR/TTS): whisper-1, tts-1, speech-… — returns no chat text. */
const SPEECH_RE = /(^|[^a-z])(whisper|tts|speech|voice|audio|transcribe|scribe)([^a-z]|$)/
/** Image/video generation: dall-e, gpt-image-1, flux, stable-diffusion … */
const IMAGE_RE =
  /(^|[^a-z])(dall[-·]?e|image-?gen|gpt-image|image-?model|flux|sdxl|stable-diffusion|seedream|imagen|sora)([^a-z]|$)/
/** Moderation classifies instead of answering. */
const MODERATION_RE = /(^|[^a-z])(omni-)?moderation([^a-z]|$)/

/**
 * Kind of a model, taken from its name. The return is deliberately always `chat`
 * when the name gives nothing away — the "other kinds" section shows only evidence.
 *
 * Special case `base`: OpenAI's Whisper family returns the bare size names
 * (tiny/base/small/medium/large); in the scan `base` sits right next to `whisper-1`
 * and is meaningless as a chat model. Only the EXACT name counts as speech —
 * `…-base`, `database`, `sbert-…` stay untouched.
 */
export function modelKind(model: string | undefined | null): ModelKind {
  if (!model) return 'chat'
  const m = model.toLowerCase().trim()
  if (isJunkModel(m)) return 'embedding'
  if (m === 'base') return 'speech'
  if (MODERATION_RE.test(m)) return 'moderation'
  if (SPEECH_RE.test(m)) return 'speech'
  if (IMAGE_RE.test(m)) return 'image'
  return 'chat'
}

/** Speech/image/moderation model — not a chat model, but really found. */
export function isNonChatModel(model: string | undefined | null): boolean {
  return modelKind(model) !== 'chat'
}

/**
 * Unfilled template: `${VAR}`, `{VAR}` or `<VAR>` in the endpoint — the
 * placeholder was never replaced by a real value (Snowflake/Databricks/
 * Infomaniak catalog entries). Such an endpoint is not usable.
 */
export function hasUnfilledTemplate(value: string | undefined | null): boolean {
  if (!value) return false
  return /\$\{[^}]*\}|(^|[^a-z0-9])\{[^}]*\}|<[^<>]+>/.test(value)
}

const LOOPBACK_RE =
  /^https?:\/\/(localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\]|0\.0\.0\.0)(:\d+)?(\/|$)/i
const PRIVATE_RE =
  /^https?:\/\/(10\.\d|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|\[fd)/i
/** Tailscale hostnames (…\.ts.net) and mDNS (.local) are private networks. */
const OVERLAY_RE = /^https?:\/\/[^/]*\.(ts\.net|local)(:\d+)?(\/|$)/i

/** Loopback endpoint (the same machine). */
export function isLoopbackEndpoint(value: string | undefined | null): boolean {
  return Boolean(value) && LOOPBACK_RE.test(String(value))
}

/** Endpoint in a private/overlay network (tailnet, RFC1918, CGNAT range). */
export function isPrivateEndpoint(value: string | undefined | null): boolean {
  if (!value) return false
  return PRIVATE_RE.test(value) || OVERLAY_RE.test(value)
}
