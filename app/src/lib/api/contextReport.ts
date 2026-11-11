/**
 * The assembled prompt as the context report shows it.
 *
 * `GET /api/context/stages` builds the stages with the same resolver a run uses,
 * so the characters counted here are the characters the model received. The
 * route is the only source; nothing on this side guesses a stage, a size or a
 * cap. A status the resolver reports stays visible even when this module has no
 * label for it, and an entry without a name is dropped instead of becoming an
 * empty row the reader would take for an empty layer.
 */
import { getContextStages } from './endpoints'

/** The status words `core/workspace_rules.py` reports for one rule file. */
export const RULE_STATUSES = [
  'included',
  'truncated',
  'empty',
  'unreadable',
  'denied',
  'skipped',
] as const

export type RuleStatus = (typeof RULE_STATUSES)[number]

export function isKnownRuleStatus(status: string): status is RuleStatus {
  return (RULE_STATUSES as readonly string[]).includes(status)
}

export interface ReportedFile {
  name: string
  /** Characters this file contributed to the prompt (what fit under a cap). */
  chars: number
  /** The resolver's status word; empty when the route did not send one. */
  status: string
  /** Stable code for a refusal or skip, e.g. `protected-root`, `no-budget`. */
  reason?: string
}

export interface ReportedStage {
  name: string
  chars: number
  /** Every candidate file the workspace-rules resolver saw, whatever happened. */
  files: ReportedFile[]
}

export interface ContextCaps {
  /** Files the resolver cut at a cap; `truncatedChars` is what still arrived. */
  truncatedFiles: number
  truncatedChars: number
  /** Files that found no room under the layer's combined cap. */
  filesWithoutBudget: number
}

export interface ContextReport {
  stages: ReportedStage[]
  totalChars: number
  caps: ContextCaps
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function asChars(value: unknown): number {
  const n = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 0
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function parseFile(raw: unknown): ReportedFile | null {
  const entry = asRecord(raw)
  const name = asText(entry?.name)
  if (!entry || !name) return null
  const reason = asText(entry.reason)
  return {
    name,
    chars: asChars(entry.chars),
    status: asText(entry.status),
    ...(reason ? { reason } : {}),
  }
}

function parseStage(raw: unknown): ReportedStage | null {
  const entry = asRecord(raw)
  const name = asText(entry?.name)
  if (!entry || !name) return null
  const files = Array.isArray(entry.files)
    ? entry.files.flatMap((file) => {
        const parsed = parseFile(file)
        return parsed ? [parsed] : []
      })
    : []
  return { name, chars: asChars(entry.chars), files }
}

function capsOf(stages: ReportedStage[]): ContextCaps {
  const caps: ContextCaps = { truncatedFiles: 0, truncatedChars: 0, filesWithoutBudget: 0 }
  for (const stage of stages) {
    for (const file of stage.files) {
      if (file.status === 'truncated') {
        caps.truncatedFiles += 1
        caps.truncatedChars += file.chars
      }
      if (file.status === 'skipped' && file.reason === 'no-budget') {
        caps.filesWithoutBudget += 1
      }
    }
  }
  return caps
}

/**
 * Normalise a `/api/context/stages` payload for display.
 *
 * A missing or unusable `total_chars` is summed from the stages, because that
 * is the number the list below it adds up to; a malformed layer or file is left
 * out rather than rendered with invented zeros.
 */
export function parseContextReport(payload: unknown): ContextReport {
  const root = asRecord(payload)
  const stages = Array.isArray(root?.stages)
    ? root.stages.flatMap((stage) => {
        const parsed = parseStage(stage)
        return parsed ? [parsed] : []
      })
    : []
  const summed = stages.reduce((sum, stage) => sum + stage.chars, 0)
  const reported = asChars(root?.total_chars)
  return {
    stages,
    totalChars: reported > 0 || summed === 0 ? reported : summed,
    caps: capsOf(stages),
  }
}

/** Fetch the prompt report; rejects when the backend does not answer. */
export async function loadContextReport(): Promise<ContextReport> {
  return parseContextReport(await getContextStages())
}
