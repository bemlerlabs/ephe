/**
 * The client half of the one plan shape. core/ephe_plan.py writes the block, the plan-mode
 * guard instructs it, and this parses it out of an answer for the surfaces that only have the
 * transcript: the card in the message and the progress section of the status popover.
 *
 * `## Plan` is a marker the surface replaces with its own translated title. A line cut off
 * mid-write parses as a shorter step, which is what keeps the card on screen while the
 * answer streams. The counts come from the marks, never from the heading digits.
 */
import type { PlanCardItem, PlanCardSpec, PlanItemStatus } from '@/types'

export type { PlanCardItem, PlanCardSpec, PlanItemStatus }

// The lines arrive trimmed, so the anchors carry no `\s*`: an optional
// whitespace run beside another one (`\s*(?:...)?\s*`) is what made these
// quadratic on a long line of spaces.
const HEADING_RE = /^(?:#+\s*)?\*{0,2}Plan\s*(?:·\s*\d+\s*\/\s*\d+)?\*{0,2}$/
const ITEM_RE = /^(?:[-*+]\s*)?\[([ >xX!-])\]\s+(\S.*)$/
const STEP_ID_RE = /^\d+[.)]\s+/

const STATUS_OF: Record<string, PlanItemStatus> = {
  ' ': 'pending',
  '>': 'active',
  x: 'done',
  X: 'done',
  '!': 'failed',
  '-': 'cancelled',
}

export function parsePlanCard(text: string): PlanCardSpec | null {
  if (!text) return null
  const items: PlanCardItem[] = []
  let headed = false
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (HEADING_RE.test(line)) {
      headed = true
      continue
    }
    const m = ITEM_RE.exec(line)
    if (!m) continue
    const title = (m[2] ?? '').replace(STEP_ID_RE, '').trim()
    if (!title) continue
    items.push({ status: STATUS_OF[m[1] ?? ' '] ?? 'pending', text: title })
  }
  // Two checklist lines without the heading still render: an answer that forgot the marker
  // is a bad heading, and the reader should not be the one to lose the plan.
  if (!items.length || (!headed && items.length < 2)) return null
  const done = items.filter((i) => i.status === 'done').length
  return { items, done, total: items.length }
}

/** The write half of the same contract: an edited plan goes back to the engine as the block
 *  it was parsed out of, so guard, emitter and parser still agree after the user's change. */
export function renderPlanBlock(titles: string[]): string {
  const clean = titles.map((t) => t.trim()).filter(Boolean)
  return ['## Plan', ...clean.map((t) => `- [ ] ${t}`)].join('\n')
}

/**
 * The composer mode a plan's execution needs.
 *
 * Plan mode is read-only by contract: `server/routes/chat.py::_mode_context` filters the
 * tools down to `_READ_ONLY_TOOL_NAMES` and appends `PLAN_MODE_GUARD`, so a turn that
 * stays in `plan` can never do what the plan describes. The write family lives in
 * `edit-auto` (`docs/COMPOSER_MODES.md`), which is why accepting a plan has to move the
 * composer there — and why that move is visible: the chip the user reads is bound to
 * `session.mode` (`ComposerModeChip.tsx` via `ChatInput.tsx`'s `storeMode` selector).
 */
export const PLAN_EXECUTION_MODE = 'edit-auto'

/**
 * The turn Accept starts: the user's line plus the plan it refers to, as the same block
 * the card was parsed out of. The engine reads the steps the user just confirmed instead
 * of a bare "proceed", which is what the dead end was made of.
 */
export function planAcceptTurn(lead: string, titles: string[]): string {
  return `${lead}\n\n${renderPlanBlock(titles)}`
}

const EVENT_STATUS: Record<string, PlanItemStatus> = {
  pending: 'pending',
  running: 'active',
  done: 'done',
  failed: 'failed',
  cancelled: 'cancelled',
}

/** The `plan` frame of the stream, in the shape the renderer takes. The frame and the text
 *  block carry the same four statuses, so both paths land on one card. */
export function planFromEvent(steps: { title: string; status: string }[]): PlanCardSpec | null {
  const items = steps
    .map((s) => ({ status: EVENT_STATUS[s.status] ?? 'pending', text: s.title.trim() }))
    .filter((s) => s.text.length > 0)
  if (!items.length) return null
  return { items, done: items.filter((i) => i.status === 'done').length, total: items.length }
}
