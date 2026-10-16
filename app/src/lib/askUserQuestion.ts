/**
 * J6 parity (point 14): AskUserQuestion — the JSON block convention.
 *
 * The model returns (optionally) a JSON block:
 *   { "question": str, "options": [{label, description?} | str], "recommendation"?, "multiSelect"? }
 * Tolerant parsing: fenced (```json) or bare blocks, trailing commas OK.
 * Pure → unit-testable without a store.
 */

export interface AskOption {
  label: string
  description?: string
}

export interface AskSpec {
  question: string
  options: AskOption[]
  recommendation?: string
  multiSelect?: boolean
}

function _tryParse(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    // Tolerance pass: strip trailing commas before }/]
    try {
      return JSON.parse(raw.replace(/,(\s*[}\]])/g, '$1'))
    } catch {
      return undefined
    }
  }
}

function _coerceOptions(value: unknown): AskOption[] | null {
  if (!Array.isArray(value) || value.length < 2) return null
  const options: AskOption[] = []
  for (const item of value) {
    if (typeof item === 'string' && item.trim()) {
      options.push({ label: item.trim() })
    } else if (
      typeof item === 'object' &&
      item !== null &&
      typeof (item as Record<string, unknown>).label === 'string'
    ) {
      const rec = item as Record<string, unknown>
      options.push({
        label: String(rec.label),
        ...(typeof rec.description === 'string' && rec.description
          ? { description: rec.description }
          : {}),
      })
    } else {
      return null
    }
  }
  return options
}

export function parseAskUserQuestion(text: string | undefined): AskSpec | null {
  if (!text) return null
  const candidates: string[] = []

  // `\s*` between the fence and the body made the pattern quadratic (it and
  // `[\s\S]*?` match the same whitespace); the body is trimmed below anyway.
  const fenceRe = /```(?:json)?([\s\S]*?)```/g
  let match: RegExpExecArray | null
  while ((match = fenceRe.exec(text)) !== null) {
    const body = String(match[1] ?? '').trim()
    if (body.startsWith('{')) candidates.push(body)
  }
  // Bare block: from { "question" … (pretty-print-tolerant) up to the text's last
  // } — convention: exactly one block per answer, nested options included
  const bareMatch = /\{\s*"question"\s*:/.exec(text)
  if (bareMatch && bareMatch.index >= 0) {
    const rest = text.slice(bareMatch.index)
    const end = rest.lastIndexOf('}')
    if (end > 0) candidates.push(rest.slice(0, end + 1))
  }

  for (const raw of candidates) {
    const parsed = _tryParse(raw)
    if (!parsed || typeof parsed !== 'object') continue
    const rec = parsed as Record<string, unknown>
    if (typeof rec.question !== 'string' || !rec.question.trim()) continue
    const options = _coerceOptions(rec.options)
    if (!options) continue
    return {
      question: rec.question.trim(),
      options,
      ...(typeof rec.recommendation === 'string' && rec.recommendation
        ? { recommendation: String(rec.recommendation).trim() }
        : {}),
      ...(rec.multiSelect === true ? { multiSelect: true } : {}),
    }
  }
  return null
}
