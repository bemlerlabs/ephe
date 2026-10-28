import { describe, expect, it } from 'vitest'
import { stripRenderedCards } from './cardText'
import { parsePlanJson } from './planCardModel'

// QD-015 W1/W2: the card and its source block are the same text. The card owns
// the reading; the prose path must not repeat the block — and a fence that is not
// a card stays exactly where it was.

const ASK = '{"question":"Which engine?","options":["Ollama","OpenAI"]}'
const PLAN = '{"steps":[{"title":"Write the test","status":"done"},{"title":"Ship it","status":"pending"}]}'

describe('stripRenderedCards', () => {
  it('drops a fenced ask block and keeps the prose around it', () => {
    const text = `Two engines fit.\n\n\`\`\`json\n${ASK}\n\`\`\`\n\nPick one.`
    expect(stripRenderedCards(text)).toBe('Two engines fit.\n\nPick one.')
  })

  it('drops a bare ask block without a fence', () => {
    const text = `Which one?\n${ASK}\nThanks.`
    expect(stripRenderedCards(text)).toBe('Which one?\n\nThanks.')
  })

  it('drops a plan JSON block, which the card now renders too', () => {
    expect(stripRenderedCards(PLAN)).toBe('')
  })

  it('keeps a fence that is not a card', () => {
    const text = '```json\n{"temperature":0.2}\n```'
    expect(stripRenderedCards(text)).toBe(text)
  })

  it('cuts a half-arrived card block while the answer streams', () => {
    const partial = 'Starting now.\n{"question":"Which engine?","options":["Oll'
    expect(stripRenderedCards(partial)).toBe('Starting now.')
  })

  it('leaves text without a block untouched', () => {
    const text = 'Plain answer, no braces.'
    expect(stripRenderedCards(text)).toBe(text)
  })

  it('is idempotent', () => {
    const once = stripRenderedCards(`Hi\n${ASK}\nbye`)
    expect(stripRenderedCards(once)).toBe(once)
  })
})

describe('parsePlanJson', () => {
  it('maps the SSE frame shape onto the card spec', () => {
    const spec = parsePlanJson(PLAN)
    expect(spec?.total).toBe(2)
    expect(spec?.done).toBe(1)
    expect(spec?.items[0]).toEqual({ status: 'done', text: 'Write the test' })
  })

  it('accepts a plain string list', () => {
    expect(parsePlanJson('{"plan":["a","b"]}')?.items.map((i) => i.text)).toEqual(['a', 'b'])
  })

  it('returns null for anything that is not a plan', () => {
    expect(parsePlanJson('{"steps":[]}')).toBeNull()
    expect(parsePlanJson('not json')).toBeNull()
  })
})
