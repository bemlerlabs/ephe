import { test, expect } from '@playwright/test'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { gradePage, floorFailures, MIN_CONTRAST_BODY } from './planPageFloors'

async function openHtml(page: Page, html: string) {
  const dir = mkdtempSync(join(tmpdir(), 'ephe-page-floor-'))
  const file = join(dir, 'page.html')
  writeFileSync(file, html, 'utf8')
  await page.goto(`file://${file}`)
}

const BARE_PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>Bare</title></head>
<body><div>Ephe — your product here. Lorem ipsum dolor sit amet, consectetur adipiscing elit.</div>
<div>Features. It is fast. It is local.</div>
<img src="https://images.example.com/stock-team.jpg" alt="team">
</body></html>`

const DESIGNED_PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ephe</title>
<style>
:root{--ink:#f4f1ea;--bg:#141210;--muted:#b8b2a6;--accent:#e2664c;
--s1:8px;--s2:16px;--s3:32px;--s4:72px;--t1:16px;--t2:20px;--t3:28px;--t4:48px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:400 var(--t1)/1.6 system-ui,sans-serif}
main{max-width:1080px;margin:0 auto;padding:0 var(--s3)}
section{padding:var(--s4) 0;border-bottom:1px solid #2a2724}
h1{font-size:var(--t4);line-height:1.1;margin:0 0 var(--s2)}
h2{font-size:var(--t3);margin:0 0 var(--s2)}
h3{font-size:var(--t2);margin:0 0 var(--s1)}
p{margin:0 0 var(--s2);color:var(--muted);max-width:62ch}
a.cta{display:inline-block;background:var(--accent);color:#1a0f0b;padding:var(--s2) var(--s3);
border-radius:8px;font-weight:600;text-decoration:none}
@media (max-width:520px){h1{font-size:34px}section{padding:var(--s3) 0}}
</style></head>
<body><main>
<section id="hero"><h1>Local-first agent for your whole workspace</h1>
<p>Ephe runs on your machine, keeps its memory on your disk and answers in the language you
type in. Nothing leaves the laptop unless you point it at an endpoint.</p>
<a class="cta" href="#install">Install Ephe</a></section>
<section id="how"><h2>How it works</h2><h3>One engine, your choice</h3>
<p>Pick a model on the machine or an endpoint on the network. Ephe starts with neither hidden
and never falls back silently.</p><h3>Plans you can read</h3>
<p>Every multi-step task arrives as a plan you accept or edit before a file changes.</p></section>
<section id="privacy"><h2>What stays on the device</h2><p>Sessions, memory, artifacts and the
audit log live under the config directory and are yours to copy, export or delete.</p></section>
<section id="install"><h2>Install</h2><p>One command, no account. The desktop build bundles the
same surface.</p><a class="cta" href="#">Get the desktop app</a></section>
</main></body></html>`

test.describe('#92 page floors', () => {
  test('the instrument refuses a bare document', async ({ page }) => {
    await openHtml(page, BARE_PAGE)
    const floors = await gradePage(page)
    const failures = floorFailures(floors)
    expect(failures.length).toBeGreaterThan(0)
    expect(failures.join('\n')).toContain('remote image')
    expect(failures.join('\n')).toMatch(/heading levels|sections|font sizes/)
  })

  test('the instrument accepts a document that meets every floor', async ({ page }) => {
    await openHtml(page, DESIGNED_PAGE)
    const floors = await gradePage(page)
    expect(floorFailures(floors), JSON.stringify(floors)).toEqual([])
    expect(floors.bodyContrast).toBeGreaterThanOrEqual(MIN_CONTRAST_BODY)
  })
})
