/**
 * F8: an unselected filter has to look like something you can press.
 *
 * Measured on both surfaces at 390x844 and 1280x800 in
 * `out/ux-fix-2026-10-10/26-f8-proof.mjs`: of the unselected controls, 0 of 4 kind chips,
 * 0 of 3 view-strip entries and 0 of 2 type chips carried an edge — `border
 * border-transparent` keeps a 1px width and paints nothing, so the row of words read as
 * headings. After: 4/4, 3/3, 2/2, at the same heights (24 px), which is why this is form
 * and not layout.
 *
 * jsdom computes no styles for these elements, so the rule is held on the class lists the
 * browser then renders. The selected branch is checked too: a border that only the
 * unselected state carries would move the label by 2 px on every tap.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const HERE = dirname(fileURLToPath(import.meta.url))
// The knowledge page joins this list once its pending panel extraction lands; its two
// branches carry the same classes and are measured in the same driver run.
const SOURCES: Array<[string, string]> = ['ArtifactsPage.tsx'].map((f) => [
  f,
  readFileSync(join(HERE, f), 'utf8'),
])

const linesOf = (src: string, re: RegExp) => src.split('\n').filter((l) => re.test(l))

describe('filter chips and view tabs carry an edge in both states', () => {
  it('leaves no control with a border that paints nothing', () => {
    for (const [file, src] of SOURCES) {
      expect(linesOf(src, /border border-transparent/), file).toEqual([])
    }
  })

  it('gives every unselected control the hairline', () => {
    const unselected =
      /: '(?:border border-hairline )?text-ink-(?:faint|soft)(?: border border-hairline)?/
    let seen = 0
    for (const [file, src] of SOURCES) {
      const rows = linesOf(src, unselected)
      expect(rows.length, file).toBeGreaterThan(0)
      for (const line of rows) {
        expect(line, `${file}: ${line.trim()}`).toContain('border border-hairline')
        seen += 1
      }
    }
    // The view tabs, the "All" chip and the kind chips.
    expect(seen).toBe(3)
  })

  it('keeps the selected branch the same width, so a tap moves no label', () => {
    for (const [file, src] of SOURCES) {
      const rows = linesOf(src, /\? 'bg-brand\/20/)
      expect(rows.length, file).toBeGreaterThan(0)
      for (const line of rows)
        expect(line, `${file}: ${line.trim()}`).toContain('border border-brand/20')
    }
  })
})
