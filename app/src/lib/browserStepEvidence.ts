/**
 * #88 — the evidence line a browser step already carries, read back off its result.
 *
 * `core/browser.py` ends every browser action with one machine line: what the page was asked
 * for, the numbers the document changed by, and a verdict of `observed` only when one of
 * those numbers actually moved. That line is the difference between a run that reports
 * itself and a run that can be checked, and until now the surface rendered the step's prose
 * and left the line inside it.
 *
 * The parse is deliberately narrow. It takes the first `STEP_EVIDENCE:` line it can read as
 * JSON and hands back nothing for anything else, because a card that shows a verdict it
 * could not read is the same class of defect as a model reporting a test it never ran. The
 * reason sentence stays in the audit row: the surface states the verdict and the numbers,
 * which need no translation to be honest, and it does not put the backend's English in front
 * of a reader who asked for German.
 */

export type StepVerdict = 'observed' | 'unproven'

/** The four counts the page was asked for, each as the change it moved by. */
export interface StepDeltas {
  elements: number
  characters: number
  scrolled: number
  checked: number
}

/** The three flags, which say that a value differed without naming the new one. */
export interface StepChanged {
  address: boolean
  title: boolean
  focus: boolean
}

export interface StepEvidence {
  step: string
  verdict: StepVerdict
  deltas: StepDeltas
  changed: StepChanged
  /** True when at least one number moved or one flag flipped — the backend's own test. */
  moved: boolean
}

const PREFIX = 'STEP_EVIDENCE:'

/** A payload the backend wrote, narrowed to the fields this surface is willing to state. */
interface RawPayload {
  step?: unknown
  verdict?: unknown
  url?: unknown
  title?: unknown
  reason?: unknown
  delta?: {
    nodes?: unknown
    text_len?: unknown
    scroll_y?: unknown
    checked?: unknown
    url_changed?: unknown
    title_changed?: unknown
    active_changed?: unknown
  }
}

const whole = (value: unknown): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 0
}

/**
 * The first `STEP_EVIDENCE:` line of a result, parsed, or null.
 *
 * Null is the answer for a step that carried no line, for a line whose JSON cannot be read,
 * and for a verdict outside the two the backend writes. Each of those is a reason to show
 * nothing, and none of them is a reason to invent a word.
 */
export function parseStepEvidence(result: string | null | undefined): StepEvidence | null {
  if (!result) return null
  const start = result.indexOf(PREFIX)
  if (start < 0) return null
  const body = result.slice(start + PREFIX.length).trim()
  const newline = body.indexOf('\n')
  const json = newline >= 0 ? body.slice(0, newline) : body
  let payload: RawPayload
  try {
    payload = JSON.parse(json) as RawPayload
  } catch {
    return null
  }
  const verdict = payload.verdict
  if (verdict !== 'observed' && verdict !== 'unproven') return null

  const delta = payload.delta ?? {}
  const deltas: StepDeltas = {
    elements: whole(delta.nodes),
    characters: whole(delta.text_len),
    scrolled: whole(delta.scroll_y),
    checked: whole(delta.checked),
  }
  const changed: StepChanged = {
    address: whole(delta.url_changed) !== 0,
    title: whole(delta.title_changed) !== 0,
    focus: whole(delta.active_changed) !== 0,
  }
  const moved =
    Object.values(deltas).some((value) => value !== 0) ||
    Object.values(changed).some((value) => value)

  return {
    step: typeof payload.step === 'string' ? payload.step : '',
    verdict,
    deltas,
    changed,
    moved,
  }
}

/** One counted fact: what moved, and by how much. */
export interface EvidenceFact {
  kind: 'elements' | 'characters' | 'scrolled' | 'checked' | 'address' | 'title' | 'focus'
  value: number
}

/**
 * What the line states, in the order a reader checks it: the counts first, then the flags.
 * A zero count is left out, because `+0 elements` would be a number about nothing, and the
 * verdict beside it already says whether the page moved.
 */
export function evidenceFacts(evidence: StepEvidence): EvidenceFact[] {
  const facts: EvidenceFact[] = []
  const { deltas, changed } = evidence
  if (deltas.elements !== 0) facts.push({ kind: 'elements', value: deltas.elements })
  if (deltas.characters !== 0) facts.push({ kind: 'characters', value: deltas.characters })
  if (deltas.scrolled !== 0) facts.push({ kind: 'scrolled', value: deltas.scrolled })
  if (deltas.checked !== 0) facts.push({ kind: 'checked', value: deltas.checked })
  if (changed.address) facts.push({ kind: 'address', value: 1 })
  if (changed.title) facts.push({ kind: 'title', value: 1 })
  if (changed.focus) facts.push({ kind: 'focus', value: 1 })
  return facts
}

/** `+19` for a gain, `-5` for a loss: the sign is the fact, so it is never dropped. */
export function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}
