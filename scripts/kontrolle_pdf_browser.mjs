// Control before the verdict: which browser shows a PDF inside a frame —
// and what does the sandbox directive do while it's at it? The first test run
// (Playwright Chromium) answered with the sad document in BOTH cases, i.e. even
// without any sandbox. That blinds the instrument, not the app. This matrix runs
// the same cases on real Chrome (channel 'chrome') and on WebKit — the
// engine-family member the desktop uses as WKWebView.
import { chromium, webkit } from '/work/ephe/app/node_modules/playwright/index.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'

const OUT = '/tmp/r5-pdf'
mkdirSync(OUT, { recursive: true })
const BASE = 'http://127.0.0.1:8765'
const FILE = '/api/artifacts/bd71841d06304b08bcb8e03ba1c4f51c/file'
const say = (l, v) => console.log(`${l}: ${v}`)

const Faelle = [
  ['dicht', 'allow-popups'],
  ['mit-origin', 'allow-popups allow-same-origin'],
  ['ohne-sandbox', null],
]

const hosts = [
  ['chrome-headless', () => chromium.launch({ headless: true }), true],
  ['chrome-echt', () => chromium.launch({ channel: 'chrome', headless: true }), true],
  ['webkit', () => webkit.launch({ headless: true }), false],
]

for (const [name, launch, isChromium] of hosts) {
  let browser
  try {
    browser = await launch()
  } catch (e) {
    say(name, 'not available: ' + String(e).slice(0, 90))
    continue
  }
  const page = await browser.newPage({ viewport: { width: 900, height: 640 } })
  // Reference: the PDF as its own page — what the browser can do at all.
  let oben = '—'
  const resp = await page.goto(BASE + FILE, { waitUntil: 'load' }).catch((e) => e)
  await page.waitForTimeout(2500)
  oben = await page.evaluate(() => document.contentType).catch(() => 'fehler')
  await page.screenshot({ path: `${OUT}/${name}-oben.png` })

  const zeilen = []
  for (const [label, sandbox] of Faelle) {
    // The iframe needs a parent living on a real origin: via about:blank the parent
    // origin is empty, and 'frame-ancestors self' rejects it. The blank frame in the
    // first run came from my measurement setup, so it says nothing about the app.
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
    const attr = sandbox ? ` sandbox="${sandbox}"` : ''
    await page.setContent(
      `<body style="margin:0"><iframe id="f" src="${BASE}${FILE}"${attr} style="width:900px;height:640px;border:0"></iframe></body>`,
    )
    await page.waitForTimeout(3500)
    // A rendered page carries strokes. Instead of guessing how full the frame is,
    // its image gets counted: a blank surface compresses to a few KB, a text page
    // to a multiple of that.
    const png = await page.screenshot()
    writeFileSync(`${OUT}/${name}-rahmen-${label}.png`, png)
    zeilen.push(`${label}=${Math.round(png.length / 1024)}KB`)
  }
  say(`${name} · Blatt`, `contentType=${oben}`)
  say(`${name} · Rahmen`, zeilen.join(' | '))
  await browser.close()
}
say('Bilder', OUT)
