// R4 sight-check, part B — the archive page against the real cards in the index.
// No seed: 31 rows, two real xlsx files, one real PNG. What gets checked is the view,
// the geometry, and what the surface claims about the file.
import { chromium } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync } from 'node:fs'

const OUT = '/tmp/r4-sicht'
mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8765'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
page.setDefaultTimeout(30_000)
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 160)))
page.on('pageerror', (e) => errors.push('pageerror: ' + String(e).slice(0, 160)))

await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)

console.log('page present:', await page.getByTestId('artifacts-page').count())
const stats = await page.getByTestId('artifacts-stats').innerText().catch(() => '(keine Kopfzahl)')
console.log('Kopfzahl:', stats)
const rows = await page.locator('[data-testid^="artifact-row-"]').count()
console.log('cards in the shelf:', rows)
const groups = await page.locator('section > h2').allInnerTexts()
console.log('Gruppen:', JSON.stringify(groups))
await page.screenshot({ path: `${OUT}/b01-regal_1440.png` })

// 1) a PDF: preview as a frame, not as a download
const pdfRow = page.locator('[data-testid^="artifact-row-"]').filter({ hasText: '.pdf' }).first()
await pdfRow.click()
await page.waitForTimeout(2500)
const frame = page.locator('[data-testid="artifact-detail"] iframe')
console.log('PDF → Frame-Vorschau:', (await frame.count()) > 0, (await frame.getAttribute('src').catch(() => '')) || '')
console.log('  sandbox:', JSON.stringify(await frame.getAttribute('sandbox').catch(() => null)))

// 2) an xlsx: the sheet must render as a table (the core of A5)
const xlsxRow = page.locator('[data-testid^="artifact-row-"]').filter({ hasText: '.xlsx' }).first()
if (await xlsxRow.count()) {
  await xlsxRow.click()
  await page.waitForTimeout(3000)
  const cells = await page.locator('[data-testid="artifact-detail"] table td').count()
  const heads = await page.locator('[data-testid="artifact-detail"] table th').allInnerTexts()
  console.log('xlsx → Zellen:', cells, '| Kopfzeile:', JSON.stringify(heads.slice(0, 8)))
  await page.screenshot({ path: `${OUT}/b02-xlsx-tabelle.png` })
} else {
  console.log('xlsx: no card in the index — preview not checked')
}

// 3) a PNG: the real image served through the id
const pngRow = page.locator('[data-testid^="artifact-row-"]').filter({ hasText: '.png' }).first()
if (await pngRow.count()) {
  await pngRow.click()
  await page.waitForTimeout(2000)
  const img = page.locator('[data-testid="artifact-detail"] img').first()
  const src = (await img.getAttribute('src')) || ''
  const ok = await img.evaluate((el) => el.complete && el.naturalWidth > 0).catch(() => false)
  console.log('png → Bild geladen:', ok, '| src:', src.slice(0, 60))
}

// 4) What does the detail view claim about the deadline and the copy?
const detail = await page.locator('[data-testid="artifact-detail"]').innerText()
const zeilen = detail.split('\n').map((s) => s.trim()).filter(Boolean)
console.log('Detail-Felder:', JSON.stringify(zeilen.filter((l) => /Frist|Kopie|Werkbank|Aufgabe|Art|Geboren/i.test(l)).slice(0, 8)))

// 5) geometry at a narrow width: 1100px, nothing may overlap
await page.setViewportSize({ width: 1100, height: 900 })
await page.waitForTimeout(1200)
await page.screenshot({ path: `${OUT}/b03-regal_1100.png` })
const blocks = await page.evaluate(() => {
  const leaf = [...document.querySelectorAll('[data-testid="artifacts-page"] *')].filter((el) => {
    if (el.children.length) return false
    const r = el.getBoundingClientRect()
    return r.width > 8 && r.height > 8
  })
  const hit = (el, x, y) => {
    const t = document.elementFromPoint(x, y)
    return t && (t === el || el.contains(t) || (t.contains && t.contains(el)))
  }
  const bad = []
  for (const el of leaf) {
    const r = el.getBoundingClientRect()
    const cx = r.left + r.width / 2
    const cy = r.top + r.height / 2
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue
    const top = document.elementFromPoint(cx, cy)
    if (top && top !== el && !el.contains(top) && !top.contains(el)) {
      const cs = getComputedStyle(top)
      if (cs.position === 'fixed' || Number(cs.zIndex || 0) >= 10) {
        bad.push({ text: (el.textContent || '').slice(0, 28), blocker: top.tagName + '.' + (top.className || '').toString().slice(0, 40), z: cs.zIndex })
      }
    }
  }
  return bad
})
console.log('overlaps at 1100px:', blocks.length, JSON.stringify(blocks.slice(0, 4)))
console.log('console errors:', errors.length, JSON.stringify(errors.slice(0, 4)))
await browser.close()
