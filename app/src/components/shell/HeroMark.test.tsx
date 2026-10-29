/**
 * S3 — the size contract of the mark, measured against the tree.
 *
 * `docs/ONBOARDING_FILM.md`: from 48 px the app carries the rendered hero; the 16–47 px
 * cut, the tray template and the in-app mark stay on the vector rig. Two slots sat at
 * exactly that size and drew the vector — the setup card (3rem) and the welcome hero
 * fallback (4rem) — and a hand-edit can put one back. So this walks every mark call in
 * `src/` and refuses a vector at or above 48 px and a render below it.
 *
 * One exception is allowed and named in the file it applies to: species `minimal` keeps
 * the vector at 4rem, because that quiet form is the user's own choice (Wave 5 decides
 * its shape). The marker below is what makes the exception visible to this test.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { render, screen } from '@testing-library/react'
import { HeroMark } from './HeroMark'

const SRC = 'src'
const MINIMAL_MARKER = 'hero-size-exception: minimal'

function walk(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (/\.(tsx|ts)$/.test(p) && !/\.(test|spec)\./.test(p)) out.push(p)
  }
  return out
}

/** A CSS length in rem or px → px. Marks are sized in these two units only. */
function toPx(size: string): number {
  if (size.endsWith('rem')) return parseFloat(size) * 16
  if (size.endsWith('px')) return parseFloat(size)
  return NaN
}

type Placement = { file: string; component: string; size: string; allowed: boolean }

const placements: Placement[] = []
for (const abs of walk(SRC)) {
  const file = relative('.', abs)
  if (file.endsWith('shell/HeroMark.tsx')) continue
  const text = readFileSync(abs, 'utf8')
  for (const m of text.matchAll(/<(EpheMark|HeroMark)\b/g)) {
    const size = /size="([^"]+)"/.exec(text.slice(m.index!, m.index! + 400))?.[1]
    if (!size) continue
    // The exception marker has to sit in the 400 characters before the element, which is
    // where its own comment lives; a marker anywhere in the file proves nothing.
    const allowed = text.slice(Math.max(0, m.index! - 400), m.index!).includes(MINIMAL_MARKER)
    placements.push({ file, component: m[1]!, size, allowed })
  }
}

describe('the mark size contract (ONBOARDING_FILM)', () => {
  it('reads the mark placements in the tree', () => {
    expect(placements.length).toBeGreaterThan(5)
  })

  it('draws no vector mark at 48 px or above', () => {
    const oversized = placements
      .filter((p) => p.component === 'EpheMark' && toPx(p.size) >= 48 && !p.allowed)
      .map((p) => `${p.file} ${p.size}`)
    expect(oversized).toEqual([])
  })

  it('renders the hero only where the contract puts it: 48 px and above', () => {
    const small = placements
      .filter((p) => p.component === 'HeroMark' && toPx(p.size) < 48)
      .map((p) => `${p.file} ${p.size}`)
    expect(small).toEqual([])
    expect(
      placements.some((p) => p.component === 'HeroMark' && /pages\/SetupPage/.test(p.file)),
    ).toBe(true)
    expect(
      placements.some((p) => p.component === 'HeroMark' && /WelcomeEmptyState/.test(p.file)),
    ).toBe(true)
  })

  it('shows the committed asset, not a redraw of it', () => {
    render(<HeroMark size="3rem" testId="guard-mark" />)
    const node = screen.getByTestId('guard-mark')
    const img = node.querySelector('img')
    expect(img?.getAttribute('src')).toBe('/onboarding/paper-moth-actor.webp')
    expect(img?.getAttribute('alt')).toBe('')
    expect(node.querySelector('svg')).toBeNull()
  })
})
