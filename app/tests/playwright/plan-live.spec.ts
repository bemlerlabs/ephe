import { test, expect } from '@playwright/test'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gradePage, floorFailures, FLOOR_LIMITS, MIN_CONTRAST_BODY } from './planPageFloors'

/**
 * #92 floors 1, 2, 5, 6, 7 and 8 on a real turn of the owner's scenario.
 *
 * This is the test that goes red when a run produces no visible plan. The measured before
 * state is 0 plans in 4 turns (docs/PLAN_SURFACE_2026-10-11.md), and every deterministic test
 * in the family passed while the product showed none of it — which is the reason this file
 * exists and the reason it costs an engine turn.
 *
 * Same discipline as app/tests/panel-conduct/live.spec.ts: without the flag the file collects
 * and does not run, so the routine suite never spends the engine.
 */
const LIVE = process.env.EPHE_PLAN_LIVE === '1'
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../out/plan-surface')
const MAX_PLAN_STEPS = 8

// The owner's sentence, typed the way he types it. The English gloss: "I need a landing page
// for my product". Kept verbatim because the request language is part of what is measured.
const SCENARIO = 'ich brauche eine Landingpage für mein Produkt' // language-gate: ignore (the measured user input, verbatim; glossed on the line above)
const FOLLOW_UP = 'Ephe, unser eigenes Produkt. Reine Marketing-Landingpage, dunkel, Deutsch.'

async function openFreshPlanSession(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de')
    localStorage.setItem('ephe_onboarded', '1')
  })
  await page.goto('/#/chat', { waitUntil: 'load' })
  await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 20_000 })
  await page.getByTestId('new-session').click()
  await page.waitForTimeout(800)
  await page.getByTestId('composer-mode-selector').click()
  await page.getByTestId('composer-mode-list').waitFor({ timeout: 4_000 })
  await page.getByTestId('composer-mode-plan').click()
  await page.waitForTimeout(400)
}

async function sendAndWait(page: import('@playwright/test').Page, text: string, budgetMs: number) {
  await page.getByTestId('chat-input').fill(text)
  await page.getByTestId('send-btn').click()
  await page
    .waitForFunction(() => !document.querySelector('[data-testid="stop-btn"]'), null, {
      timeout: budgetMs,
      polling: 1_000,
    })
    .catch(() => console.log('plan-live: turn still streaming at the ceiling'))
  await page.waitForTimeout(1_500)
}

test.describe.configure({ mode: 'serial' })

test('plan mode ends in a readable plan the user can answer', async ({ page }) => {
  test.skip(!LIVE, 'set EPHE_PLAN_LIVE=1 to spend a real engine turn')
  test.setTimeout(600_000)
  await openFreshPlanSession(page)
  await sendAndWait(page, SCENARIO, 420_000)

  const card = page.getByTestId('plan-card')
  await expect(card, 'the turn produced no plan the reader can see').toBeVisible({
    timeout: 5_000,
  })
  const rows = card.locator('[data-testid^="plan-item-"]')
  const named = await rows.count()
  console.log(`plan-live PLAN-STEPS ${named}`)
  expect(named, `floor: 4 to 8 steps, saw ${named}`).toBeGreaterThanOrEqual(
    FLOOR_LIMITS.MIN_SECTIONS,
  )
  expect(named).toBeLessThanOrEqual(MAX_PLAN_STEPS)
  for (const i of Array.from({ length: named }, (_, k) => k)) {
    const text = (await rows.nth(i).innerText()).trim()
    expect(text.length, 'a step that reads as one word is not a step').toBeGreaterThanOrEqual(12)
  }
  await page.screenshot({ path: join(OUT, 'live-01-plan.png'), fullPage: true })

  // Floor 6: the plan is editable, and what is sent is the edited block.
  await card.getByTestId('plan-edit').click()
  await expect(card.getByTestId('plan-editor')).toBeVisible()
  const first = card.getByTestId('plan-step-input-0')
  const edited = `${(await first.inputValue()).trim()} (edited by the user)`
  await first.fill(edited)
  await card.getByTestId('plan-edit-send').click()
  const sent = page.locator('[data-testid="message-bubble"][data-role="user"]')
  await expect(sent.last()).toContainText('Plan')
  await expect(sent.last()).toContainText('(edited by the user)')
  await page.screenshot({ path: join(OUT, 'live-02-plan-edited.png'), fullPage: true })

  // Floor 5: accept answers the plan and the run starts under it.
  await openFreshPlanSession(page)
  await sendAndWait(page, SCENARIO, 420_000)
  const second = page.getByTestId('plan-card')
  await expect(second).toBeVisible({ timeout: 5_000 })
  await second.getByTestId('plan-accept').click()
  await expect(second.getByTestId('plan-accepted')).toBeVisible()
  await expect(second.getByTestId('plan-accept')).toHaveCount(0)
  await page.screenshot({ path: join(OUT, 'live-03-plan-accepted.png'), fullPage: true })
})

test('the page a run produces reads as designed', async ({ page, request }) => {
  test.skip(!LIVE, 'set EPHE_PLAN_LIVE=1 to spend a real engine turn')
  test.setTimeout(900_000)
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de')
    localStorage.setItem('ephe_onboarded', '1')
  })
  await page.goto('/#/chat', { waitUntil: 'load' })
  await page.waitForSelector('[data-testid="panel-chat"]', { timeout: 20_000 })
  await page.getByTestId('new-session').click()
  await page.waitForTimeout(800)
  await sendAndWait(page, SCENARIO, 300_000)
  await sendAndWait(page, FOLLOW_UP, 600_000)

  const listed = await request.get('/api/artifacts')
  expect(listed.ok()).toBeTruthy()
  const body = (await listed.json()) as {
    artifacts?: { id: string; filename?: string; title?: string }[]
  }
  const html = (body.artifacts ?? []).find((a) => /\.html?$/i.test(a.filename ?? a.title ?? ''))
  test.info().annotations.push({
    type: 'artifact',
    description: html ? `graded ${html.filename ?? html.title}` : 'no html artifact in the turn',
  })
  expect(html, 'the run left no HTML artifact to inspect').toBeDefined()

  const file = await request.get(`/api/artifacts/${html!.id}/file`)
  expect(file.ok()).toBeTruthy()
  const dir = mkdtempSync(join(tmpdir(), 'ephe-live-page-'))
  const path = join(dir, 'produced.html')
  writeFileSync(path, await file.text(), 'utf8')
  await page.goto(`file://${path}`)

  const floors = await gradePage(page)
  const failures = floorFailures(floors)
  console.log(`plan-live PAGE-FLOORS ${JSON.stringify(floors)}`)
  console.log(`plan-live PAGE-FAILURES ${JSON.stringify(failures)}`)
  await page.screenshot({ path: join(OUT, 'live-04-produced-page.png'), fullPage: true })
  expect(failures, JSON.stringify(floors)).toEqual([])
  expect(floors.bodyContrast).toBeGreaterThanOrEqual(MIN_CONTRAST_BODY)
})
