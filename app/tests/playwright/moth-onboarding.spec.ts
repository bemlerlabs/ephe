import { test, expect, type Page } from '@playwright/test'

/*
 * brand-eng (2026-11-24): the first open carries the paper moth.
 *
 * The figure that used to stand in the first run is gone from the tree, and the
 * moth took its place with the same job: be born out of the film's fire, walk the
 * three questions, and land in the header. These cases look at the three places a
 * person meets it — the film's birth, the tour's guide, and the welcome hero of a
 * machine that still stores the removed form — because each of those reads its
 * figure from a different module and only the last one is covered by a unit test.
 *
 * Reduced motion runs here as both switches: the operating system's
 * `prefers-reduced-motion` and the product's own `appearance.animations_enabled`,
 * which is what paints `html.no-motion`. A first open that only works while moving
 * is not a first open.
 */

const SETTINGS_BASE = {
  provider: {
    type: 'openai_compatible',
    model: 'fixture-model',
    endpoint: 'http://127.0.0.1:9/v1',
  },
  language: 'de',
  theme: 'dark',
  memory_enabled: true,
}

function appearanceField(
  key: string,
  type: 'bool' | 'select',
  value: boolean | string,
  options?: string[],
) {
  return {
    key,
    type,
    label: key,
    labelEn: key,
    default: value,
    value,
    ...(options ? { options } : {}),
  }
}

/** The deep register, as the server sends it: sections carrying fields. */
function deepSettings(fields: ReturnType<typeof appearanceField>[]) {
  return [{ key: 'appearance', fields }]
}

async function stubApi(page: Page, deep: unknown[] = []) {
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    const json = (body: unknown) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/api/setup/status') {
      return json({
        configured: true,
        skipped: false,
        provider: 'openai_compatible',
        model: 'fixture-model',
        url: null,
      })
    }
    if (path === '/api/settings') return json({ ...SETTINGS_BASE, deep })
    if (path === '/api/plugins') {
      return json({
        version: 1,
        master_enabled: true,
        read_only: false,
        unproven: false,
        notices: [],
        public: [],
        personal: [],
        installed: [],
        orphans: [],
        contested: { tools: [], memory_providers: [] },
      })
    }
    if (path === '/api/market/installed') return json({ plugins: [] })
    if (path === '/api/health') {
      return json({
        status: 'ok',
        models: ['fixture-model'],
        active_model: 'fixture-model',
        active_provider: 'openai_compatible',
        engine_online: true,
        engine_state: 'ok',
        model_installed: true,
        ollama: false,
      })
    }
    return json({})
  })
}

async function openFirstRun(page: Page, deep: unknown[] = [], replayTour = false) {
  await stubApi(page, deep)
  await page.addInitScript(() => localStorage.clear())
  // `?tour=1` is the product's own replay door (tourForceFromUrl); the stubbed
  // /api/setup/status reports a configured machine, and a configured machine that
  // has been through the tour once is exactly the case that door exists for.
  await page.goto(replayTour ? '/?tour=1#/' : '/#/', { waitUntil: 'load' })
  await expect(page.getByTestId('first-run-intro')).toBeVisible({ timeout: 10000 })
}

/** Past the film and past the questions, so the welcome screen underneath is the subject. */
async function walkPastTheTour(page: Page) {
  const skip = page.getByTestId('intro-skip')
  if (await skip.isVisible().catch(() => false)) await skip.click()
  await page
    .getByTestId('first-run-intro')
    .waitFor({ state: 'detached', timeout: 5000 })
    .catch(() => {})
  for (let step = 0; step < 8; step += 1) {
    const next = page
      .getByTestId('tour-start')
      .or(page.getByTestId('tour-continue'))
      .or(page.getByTestId('tour-finish'))
      .first()
    if (!(await next.isVisible().catch(() => false))) break
    await next.click()
  }
  await page
    .getByTestId('first-run-tour')
    .waitFor({ state: 'detached', timeout: 5000 })
    .catch(() => {})
}

test.use({ serviceWorkers: 'block' })

test.describe('the first open carries the moth', () => {
  test('births the moth out of the film, with no other creature in the scene', async ({ page }) => {
    await openFirstRun(page)

    const figure = page.locator('.intro-live-moth')
    await expect(figure).toHaveCount(1)
    const body = figure.locator('img.intro-live-moth-body')
    await expect(body).toHaveCount(1)
    expect(await body.getAttribute('src')).toContain('paper-moth-actor.webp')
    // The two hinged halves are the moth's own wings, not another figure's parts.
    const wings = await figure
      .locator('img.intro-live-wing')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('src')))
    expect(wings).toEqual([
      '/onboarding/paper-moth-wing-l.webp',
      '/onboarding/paper-moth-wing-r.webp',
    ])

    // Nothing in the running document still names the removed figure.
    const named = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[class],[data-testid],[src]'))
        .map(
          (node) =>
            `${node.className} ${node.getAttribute('data-testid') ?? ''} ${node.getAttribute('src') ?? ''}`,
        )
        .filter((line) => /bee|biene/i.test(line)),
    )
    expect(named).toEqual([])
  })

  test('walks the questions with the moth as the guide', async ({ page }) => {
    await openFirstRun(page, [], true)
    await page.getByTestId('intro-skip').click()

    const tour = page.getByTestId('first-run-tour')
    await expect(tour).toBeVisible({ timeout: 10000 })
    // Step nought is the tour's own opening; the guide walks in with the questions.
    const start = page.getByTestId('tour-start')
    await expect(start).toBeVisible()
    await start.click()

    const guide = page.getByTestId('interactive-moth-guide')
    await expect(guide).toBeVisible({ timeout: 10000 })
    const guideBox = await guide.boundingBox()
    expect(guideBox).not.toBeNull()
    expect(guideBox!.width).toBeGreaterThan(40)
    expect(await guide.locator('img.moth-actor-body').getAttribute('src')).toBe(
      '/onboarding/paper-moth-actor.webp',
    )

    const next = page.getByTestId('tour-continue').first()
    await expect(next).toBeVisible()
    await next.click()
    await expect(page.getByTestId('tour-panel')).toBeVisible()
  })

  test('keeps the moth on the stage when motion is off, standing still and answerable', async ({
    page,
  }) => {
    await openFirstRun(
      page,
      deepSettings([appearanceField('appearance.animations_enabled', 'bool', false)]),
      true,
    )
    await page.getByTestId('intro-skip').click()

    await expect(page.getByTestId('first-run-tour')).toBeVisible({ timeout: 10000 })
    // The product's own switch, not only the operating system's.
    await expect(page.locator('html')).toHaveClass(/no-motion/)
    await page.getByTestId('tour-start').click()

    const guide = page.getByTestId('interactive-moth-guide')
    await expect(guide).toBeVisible({ timeout: 10000 })
    const guideBox = await guide.boundingBox()
    expect(guideBox).not.toBeNull()
    expect(guideBox!.width).toBeGreaterThan(40)
    // The same figure, not a placeholder: body, wings, and the thread it rose on.
    expect(await guide.locator('img.moth-actor-body').getAttribute('src')).toBe(
      '/onboarding/paper-moth-actor.webp',
    )
    expect(await guide.locator('img.moth-actor-wing').count()).toBe(2)
    // Standing means standing: every animation under the guide resolves to none, and
    // the spark canvas — a thing that cannot exist still — is not mounted at all.
    expect(
      await guide
        .locator('.moth-actor-motion')
        .evaluate((el) => getComputedStyle(el).animationName),
    ).toBe('none')
    expect(
      await guide
        .locator('img.moth-actor-wing')
        .first()
        .evaluate((el) => getComputedStyle(el).animationName),
    ).toBe('none')
    await expect(page.locator('canvas.moth-guide-sparks')).toHaveCount(0)

    // And the questions stay reachable beside the still figure.
    const panel = page.getByTestId('tour-panel')
    await expect(panel).toBeVisible()
    const next = page.getByTestId('tour-continue').first()
    await expect(next).toBeVisible()
    await next.click()
    await expect(panel).toBeVisible()
  })

  test('opens a machine that stored the removed form on the moth, not on an empty box', async ({
    page,
  }) => {
    await openFirstRun(
      page,
      deepSettings([
        appearanceField('appearance.companion_enabled', 'bool', true),
        appearanceField('appearance.companion_species', 'select', 'fire_bee', [
          'paper_moth',
          'ember_spark',
          'minimal',
        ]),
      ]),
    )
    await walkPastTheTour(page)
    await page.goto('/#/chat', { waitUntil: 'load' })

    const hero = page.getByTestId('ephe-mark-hero')
    await expect(hero).toBeVisible({ timeout: 10000 })
    expect(await hero.getAttribute('data-species')).toBe('paper_moth')
    expect(await hero.locator('img.companion-body').getAttribute('src')).toBe(
      '/onboarding/paper-moth-actor.webp',
    )
  })
})
