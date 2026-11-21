/**
 * W-4 — the shelf names every kind the index can store, in the reader's language.
 *
 * `kindLabel` (shelf.tsx) reads `artifacts.kind.<kind>` and falls back to the kind
 * uppercased. That fallback is what a person saw: group headers reading MANIFEST,
 * SCORECARD, QA, EVIDENCE_LEDGER, DECK_SPEC, RENDER_QA above a shelf whose every other
 * word was English or German. The kinds are not a UI list — they come from the marker
 * table the producing tools write through, so nothing in the frontend said when a new
 * one arrived without a name.
 *
 * This test reads the table where it lives. It fails on the first kind that has no leaf
 * in either bundle, and on a pair that drifted apart.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import en from '@/locales/en.json'
import de from '@/locales/de.json'

function findRepo(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), '..')]) {
    if (existsSync(resolve(base, 'core', 'artifact_markers.py'))) return base
  }
  throw new Error(`core/artifact_markers.py not found below ${process.cwd()}`)
}

/** Rows are `(marker, kind, label, activity_word, with_name)`; `kind` is the second field. */
const MARKER_ROWS = /^\s*\("([A-Z][A-Z0-9_]*_FILE:)",\s*"([a-z][a-z0-9_]*)",\s*"/gm

function storedKinds(): string[] {
  const source = readFileSync(resolve(findRepo(), 'core', 'artifact_markers.py'), 'utf-8')
  return [...source.matchAll(MARKER_ROWS)].map((row) => row[2]!)
}

const kinds = [...new Set(storedKinds())]

/** For a file type the shout IS the word a reader expects; for a name it is the fallback. */
const FILE_TYPES = new Set([
  'pdf',
  'svg',
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'xlsx',
  'docx',
  'pptx',
  'csv',
])

describe('every artifact kind has a word in both bundles', () => {
  it('reads the marker table, not a hand-copied list', () => {
    // The 27 rows of the table carry these kinds; a list that shrinks to two means the
    // regex stopped matching the file's shape, and the gate below would pass on nothing.
    expect(kinds.length).toBeGreaterThanOrEqual(20)
  })

  it.each(kinds)('%s is named, not uppercased', (kind) => {
    const enWord = (en.artifacts.kind as Record<string, string>)[kind] ?? ''
    const deWord = (de.artifacts.kind as Record<string, string>)[kind] ?? ''
    expect(enWord, `en.json artifacts.kind.${kind}`).toBeTruthy()
    expect(deWord, `de.json artifacts.kind.${kind}`).toBeTruthy()
    if (!FILE_TYPES.has(kind)) {
      // A label that is the kind shouting is the fallback, not a name.
      expect(enWord).not.toBe(kind.toUpperCase())
      expect(deWord).not.toBe(kind.toUpperCase())
    }
    // Sentence case in both bundles: a chip that shouts is the fallback shape.
    expect(enWord.slice(0, 1)).toBe(enWord.slice(0, 1).toUpperCase())
    expect(deWord.slice(0, 1)).toBe(deWord.slice(0, 1).toUpperCase())
  })
})
