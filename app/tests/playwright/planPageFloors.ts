import type { Page } from '@playwright/test'

/**
 * #92 floor 8: a page Ephe generated has to read as designed. These are the same countable
 * floors docs/PLAN_SURFACE_2026-10-11.md section 5 states and PAGE_OUTPUT_GUARD instructs,
 * measured on the rendered document (computed styles, real contrast, real overflow) rather
 * than on the HTML source.
 *
 * The grader is proven here against two documents it must disagree about, so a green run of
 * the live leg means the instrument looked at the page. The live leg itself is
 * plan-live.spec.ts.
 */

export interface PageFloors {
  h1: number
  headingLevels: number
  sections: number
  fontSizes: number
  scaleRatio: number
  bodyContrast: number
  overflowAt390: boolean
  overflowAt1280: boolean
  emojiInHeading: boolean
  remoteStockImage: boolean
}

export const MIN_CONTRAST_BODY = 4.5
const MIN_FONT_STEPS = 4
const MIN_SECTIONS = 4
const MIN_HEADING_LEVELS = 3
const MIN_SCALE_RATIO = 1.25

export const FLOOR_LIMITS = {
  MIN_CONTRAST_BODY,
  MIN_FONT_STEPS,
  MIN_SECTIONS,
  MIN_HEADING_LEVELS,
  MIN_SCALE_RATIO,
}

function contrastOf(fg: { r: number; g: number; b: number }, lum: number) {
  const lin = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  const l = 0.2126 * lin(fg.r) + 0.7152 * lin(fg.g) + 0.0722 * lin(fg.b)
  const [a, b] = l > lum ? [l, lum] : [lum, l]
  return (a + 0.05) / (b + 0.05)
}

/** Reads the rendered document: the sizes the browser computed, the colours it painted. */
export async function gradePage(page: Page): Promise<PageFloors> {
  const raw = await page.evaluate(() => {
    const px = (v: string) => {
      const m = /([\d.]+)/.exec(v)
      return m ? Number(m[1]) : 0
    }
    const parseRgb = (v: string) => {
      const m = /rgba?\(([^)]+)\)/.exec(v)
      const parts = (m?.[1] ?? '').split(',').map((s) => Number(s.trim()))
      return {
        r: parts[0] ?? 0,
        g: parts[1] ?? 0,
        b: parts[2] ?? 0,
        a: parts.length > 3 ? parts[3]! : 1,
      }
    }
    const body = document.body
    const bodyStyle = getComputedStyle(body)
    // The painted background of the body, walked up until a non-transparent one answers.
    let bg = parseRgb(bodyStyle.backgroundColor)
    let node: HTMLElement | null = body
    while ((bg.a === 0 || (bg.r === 0 && bg.g === 0 && bg.b === 0)) && node?.parentElement) {
      node = node.parentElement
      bg = parseRgb(getComputedStyle(node).backgroundColor)
    }
    const levels = new Set<number>()
    for (const h of Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))) {
      levels.add(Number(h.tagName[1]))
    }
    const sectionish = document.querySelectorAll('section, main > div, [data-section]')
    let sections = 0
    for (const s of Array.from(sectionish)) {
      if (s.querySelector('h1,h2,h3')) sections += 1
    }
    const sizes = new Set<number>()
    for (const el of Array.from(document.querySelectorAll('h1,h2,h3,p,li,a,span,body'))) {
      const fs = px(getComputedStyle(el).fontSize)
      if (fs > 0) sizes.add(Math.round(fs * 10) / 10)
    }
    const sorted = Array.from(sizes).sort((a, b) => a - b)
    let ratio = 0
    for (let i = 1; i < sorted.length; i++) {
      const r = sorted[i]! / sorted[i - 1]!
      if (r > 1.02 && (ratio === 0 || r < ratio)) ratio = r
    }
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4'))
    const emoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/u
    return {
      h1: document.querySelectorAll('h1').length,
      headingLevels: levels.size,
      sections,
      fontSizes: sorted.length,
      scaleRatio: Number(ratio.toFixed(2)),
      bodyColor: parseRgb(bodyStyle.color),
      bgColor: bg,
      emojiInHeading: headings.some((h) => emoji.test(h.textContent ?? '')),
      remoteStockImage: Array.from(document.querySelectorAll('img')).some((i) =>
        /^https?:\/\//i.test(i.getAttribute('src') ?? ''),
      ),
    }
  })
  const lumOf = (c: { r: number; g: number; b: number }) => {
    const lin = (v: number) => {
      const s = v / 255
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
    }
    return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b)
  }
  const body = await page.evaluate(() => document.body.scrollWidth)
  await page.setViewportSize({ width: 390, height: 844 })
  const at390 = await page.evaluate(() => document.body.scrollWidth)
  await page.setViewportSize({ width: 1280, height: 900 })
  const at1280 = await page.evaluate(() => document.body.scrollWidth)
  void body
  return {
    h1: raw.h1,
    headingLevels: raw.headingLevels,
    sections: raw.sections,
    fontSizes: raw.fontSizes,
    scaleRatio: raw.scaleRatio,
    bodyContrast: Number(contrastOf(raw.bodyColor, lumOf(raw.bgColor)).toFixed(2)),
    overflowAt390: at390 > 391,
    overflowAt1280: at1280 > 1281,
    emojiInHeading: raw.emojiInHeading,
    remoteStockImage: raw.remoteStockImage,
  }
}

export function floorFailures(f: PageFloors): string[] {
  const bad: string[] = []
  if (f.h1 !== 1) bad.push(`h1=${f.h1}, expected exactly 1`)
  if (f.headingLevels < FLOOR_LIMITS.MIN_HEADING_LEVELS)
    bad.push(`heading levels=${f.headingLevels}, floor ${FLOOR_LIMITS.MIN_HEADING_LEVELS}`)
  if (f.sections < FLOOR_LIMITS.MIN_SECTIONS)
    bad.push(`sections=${f.sections}, floor ${FLOOR_LIMITS.MIN_SECTIONS}`)
  if (f.fontSizes < FLOOR_LIMITS.MIN_FONT_STEPS)
    bad.push(`font sizes=${f.fontSizes}, floor ${FLOOR_LIMITS.MIN_FONT_STEPS}`)
  if (f.scaleRatio < FLOOR_LIMITS.MIN_SCALE_RATIO)
    bad.push(`scale ratio=${f.scaleRatio}, floor ${FLOOR_LIMITS.MIN_SCALE_RATIO}`)
  if (f.bodyContrast < MIN_CONTRAST_BODY)
    bad.push(`body contrast=${f.bodyContrast}, floor ${MIN_CONTRAST_BODY}`)
  if (f.overflowAt390) bad.push('horizontal scroll at 390px')
  if (f.overflowAt1280) bad.push('horizontal scroll at 1280px')
  if (f.emojiInHeading) bad.push('emoji in a heading')
  if (f.remoteStockImage) bad.push('remote image')
  return bad
}
