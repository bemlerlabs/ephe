/**
 * QD-015 W1: a card's own source block must not also be read as text.
 *
 * The engine writes the AskUserQuestion block as JSON, and now also a plan as a
 * JSON `steps` list. The bubble renders the interactive card from that same
 * text, so without a cut the reader saw the code block above the card. Only a
 * block that actually parses as one of those cards is removed; every other
 * fence — a config snippet, an A2UI surface, a pasted document — stays.
 */
import { parseAskUserQuestion } from './askUserQuestion'
import { parsePlanJson } from './planCardModel'

const CARD_KEY_START = /^\{\s*"(?:question|steps|plan)"\s*:/

/** Fenced block: the fence itself is part of what disappears. */
const FENCE_RE = /```[ \t]*(?:json)?[ \t]*\n?([\s\S]*?)```/g

function isCardJson(body: string): boolean {
  const trimmed = body.trim()
  if (!CARD_KEY_START.test(trimmed)) return false
  return parseAskUserQuestion(trimmed) !== null || parsePlanJson(trimmed) !== null
}

/** End index (exclusive) of the top-level object starting at `start`, or -1 while
 *  it is still arriving. String state matters: a brace inside a question text
 *  must not close the block early. */
function objectEnd(text: string, start: number): number {
  let depth = 0
  let inString = false
  let escaped = false
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i]
    if (inString) {
      if (escaped) escaped = false
      else if (ch === '\\') escaped = true
      else if (ch === '"') inString = false
      continue
    }
    if (ch === '"') inString = true
    else if (ch === '{') depth += 1
    else if (ch === '}') {
      depth -= 1
      if (depth === 0) return i + 1
    }
  }
  return -1
}

/** Removes every card block from an answer. Idempotent; text without a `{` is
 *  returned as it came. */
export function stripRenderedCards(text: string): string {
  if (!text || !text.includes('{')) return text
  let out = text.replace(FENCE_RE, (whole: string, body: string) =>
    isCardJson(String(body)) ? '' : whole,
  )
  let cursor = 0
  for (;;) {
    const open = out.indexOf('{', cursor)
    if (open < 0) break
    const head = out.slice(open, open + 200)
    if (!CARD_KEY_START.test(head)) {
      cursor = open + 1
      continue
    }
    const end = objectEnd(out, open)
    if (end < 0) {
      // Still arriving: drop the partial block and everything after it, so the
      // reader never watches the JSON type itself out.
      out = out.slice(0, open)
      break
    }
    const candidate = out.slice(open, end)
    if (isCardJson(candidate)) {
      out = out.slice(0, open) + out.slice(end)
      cursor = open
    } else {
      cursor = open + 1
    }
  }
  return out.replace(/\n{3,}/g, '\n\n').trim()
}
