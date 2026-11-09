/**
 * #28 — the pure model behind the creator card.
 *
 * A creator turn answers with JSON, so the card reads its facts out of those answers and
 * nowhere else: the bundle's name, the files staged so far, the verdict of the most recent
 * verification and the outcome of an install. Nothing here guesses from prose — a result
 * that is not one of the four payloads adds a pending count or a refusal code, never a
 * file, a version or a digest. The shapes are the ones `core/tools/creator_tools.py`
 * writes; the test next to this file pins each of them.
 */

export const CREATOR_TOOLS: ReadonlySet<string> = new Set([
  'create_plugin_scaffold',
  'write_plugin_source',
  'verify_plugin_bundle',
  'install_plugin_bundle',
])

/** Structure-free shadow of a tool call, the same shape `toolStreamModel` uses. */
export interface CreatorCallShape {
  id?: string
  name: string
  args?: unknown
  result?: unknown
  status?: unknown
}

export interface CreatorPluginModel {
  /** The bundle this turn is authoring; '' when no answer and no call names one. */
  name: string
  version: string
  license: string
  publisher: string
  /** Bundle-relative paths, in the order the answers showed them. */
  files: string[]
  /** How many source writes answered. */
  writes: number
  /** A scaffold answer is the only proof that anything is staged. */
  staged: boolean
  verified: boolean
  /** The newest verification's problems; empty when it passed or none arrived. */
  problems: string[]
  /** Tools the newest verification read off the manifest. */
  tools: string[]
  sha256: string
  installed: boolean
  enabled: boolean
  trust: string
  warning: string
  /** The newest answer's refusal code; '' while the last answer was accepted. */
  error: string
  /** Calls that have not answered yet — the streaming case. */
  pending: number
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function strArray(v: unknown): string[] {
  return Array.isArray(v) ? v.map(str).filter((s) => s !== '') : []
}

/** The answer body, or null when the call has not answered or said something else. */
function payloadOf(result: unknown): Record<string, unknown> | null {
  const text = str(result)
  if (!text) return null
  const trimmed = text.trimStart()
  if (!trimmed.startsWith('{')) return null
  try {
    const parsed: unknown = JSON.parse(trimmed)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

function argName(call: CreatorCallShape): string {
  const args = argsOf(call)
  return args ? str(args.name) || str(args.bundle) : ''
}

function argsOf(call: CreatorCallShape): Record<string, unknown> | null {
  const args = call.args
  return args && typeof args === 'object' ? (args as Record<string, unknown>) : null
}

export function creatorModelFor(calls: CreatorCallShape[]): CreatorPluginModel | null {
  const creator = calls.filter((c) => CREATOR_TOOLS.has(c.name))
  if (creator.length === 0) return null

  const model: CreatorPluginModel = {
    name: '',
    version: '',
    license: '',
    publisher: '',
    files: [],
    writes: 0,
    staged: false,
    verified: false,
    problems: [],
    tools: [],
    sha256: '',
    installed: false,
    enabled: false,
    trust: '',
    warning: '',
    error: '',
    pending: 0,
  }
  let answeredName = ''

  for (const call of creator) {
    const payload = payloadOf(call.result)
    if (!payload) {
      if (str(call.result)) continue
      model.pending += 1
      continue
    }
    const error = str(payload.error)
    if (error) model.error = error
    else model.error = ''

    if (str(payload.name)) {
      answeredName = str(payload.name)
      model.name = answeredName
    }
    if (str(payload.version)) model.version = str(payload.version)
    if (str(payload.license)) model.license = str(payload.license)
    if (str(payload.publisher)) model.publisher = str(payload.publisher)
    if (str(payload.sha256)) model.sha256 = str(payload.sha256)
    if (str(payload.warning)) model.warning = str(payload.warning)

    if (call.name === 'create_plugin_scaffold' && !error) {
      model.staged = true
      for (const file of strArray(payload.files)) {
        if (!model.files.includes(file)) model.files.push(file)
      }
    }
    if (call.name === 'write_plugin_source' && !error) {
      model.writes += 1
      const path = str(payload.path) || str(argsOf(call)?.path)
      if (path && !model.files.includes(path)) model.files.push(path)
    }
    if (call.name === 'verify_plugin_bundle') {
      model.verified = payload.ok === true
      model.problems = error ? strArray(payload.problems) : []
      model.tools = model.verified ? strArray(payload.tools) : []
    }
    if (call.name === 'install_plugin_bundle') {
      model.installed = str(payload.status) === 'installed'
      model.enabled = model.installed ? payload.enabled === true : false
      model.trust = model.installed ? str(payload.trust) : ''
    }
  }

  if (!model.name) model.name = creator.map(argName).filter(Boolean).pop() ?? ''
  return model
}
