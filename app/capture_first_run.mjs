// First-run scene harness — every stage of the scene, in both themes, plus the two states
// that must not draw it.
//
// One stub stands in for the external thing the handover depends on: GET /api/setup/status
// answers "no engine chosen" (the new visitor) or "chosen", so the surface behind the
// overlay is a real one — the engine offer or the empty chat — instead of an error page.
// GET /api/settings answers an empty register and GET /api/sessions an empty list, which is
// what the app would get from a backend with nothing stored.
//
// Usage (vite dev on 5173 must be running):
//   cd app && npm run dev          # in one shell
//   cd app && node capture_first_run.mjs
//
// Optional: EPHE_BASE (default http://127.0.0.1:5173), EPHE_CHROME (browser binary),
// EPHE_OUT (screenshot directory, default test-results/first-run).
//
// The run asserts the real DOM at every stage: the overlay is a dialog that names itself,
// the skip control is on screen and reachable in the first frame, the app is mounted behind
// the overlay while the scene runs, the button carries the sheet's own delay, the clock ends
// the scene and writes the install flag, a browser that carries the flag gets no scene, and
// a viewer who asked for less motion gets one still that closes by itself. Every check
// prints one JSON fact; exit code 1 if any of them failed.
import { chromium } from '@playwright/test';
import { existsSync, mkdirSync } from 'node:fs';

const BASE = process.env.EPHE_BASE || 'http://127.0.0.1:5173';
const OUT = process.env.EPHE_OUT || 'test-results/first-run';
const CACHED_CHROME =
  undefined;
const EXE = process.env.EPHE_CHROME || (existsSync(CACHED_CHROME) ? CACHED_CHROME : undefined);

const VIEWPORT = { width: 1280, height: 820 };
const SEEN_KEY = 'ephe.intro.seen.v1';
const GATE_HINT_KEY = 'ephe.setup_gate';

mkdirSync(OUT, { recursive: true });
const facts = { base: BASE, chrome: EXE || 'bundled chromium', shots: [], facts: {}, failures: [] };

function check(name, ok, detail) {
  facts.facts[name] = { ok: Boolean(ok), detail };
  if (!ok) facts.failures.push(`${name}: ${JSON.stringify(detail)}`);
}

const browser = await chromium.launch({ ...(EXE ? { executablePath: EXE } : {}), headless: true });

/** One context with the stubs in place. `seen` pre-loads the install flag. */
async function open({ theme = 'light', reducedMotion = 'no-preference', configured = false, seen = false } = {}) {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    colorScheme: theme === 'dark' ? 'dark' : 'light',
    reducedMotion,
  });
  if (theme === 'dark') {
    await context.addInitScript(() => window.localStorage.setItem('ephe.theme', 'dark'));
  }
  await context.route('**/api/setup/status', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ready: true, configured, skipped: false }),
    }),
  );
  await context.route('**/api/settings', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ deep: [] }) }),
  );
  await context.route('**/api/sessions', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
  );
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  if (seen) {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await page.evaluate(
      ([seenKey, gateKey]) => {
        window.localStorage.setItem(seenKey, '1');
        window.localStorage.setItem(gateKey, JSON.stringify({ ready: true, configured: true, skipped: false }));
      },
      [SEEN_KEY, GATE_HINT_KEY],
    );
  }
  const started = Date.now();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  return { page, context, errors, started };
}

/** The overlay's own state, read from the live DOM. */
const stateOf = (page) =>
  page.evaluate(() => {
    const overlay = document.querySelector('[data-testid="first-run-intro"]');
    const reading = (selector) => {
      const el = document.querySelector(selector);
      return el ? { opacity: getComputedStyle(el).opacity, delay: el.style.animationDelay } : null;
    };
    return {
      overlay: overlay
        ? {
            role: overlay.getAttribute('role'),
            modal: overlay.getAttribute('aria-modal'),
            labelled: Boolean(overlay.getAttribute('aria-labelledby')),
            described: Boolean(overlay.getAttribute('aria-describedby')),
            phase: overlay.getAttribute('data-phase'),
            reduced: overlay.getAttribute('data-reduced'),
            markState: document.querySelector('[data-testid="intro-mark"]')?.getAttribute('data-state'),
          }
        : null,
      title: reading('[data-testid="first-run-intro"] h1'),
      cta: reading('[data-testid="intro-cta"]'),
      skip: reading('[data-testid="intro-skip"]'),
      appBehind: {
        rootChildren: document.querySelector('#root')?.children.length ?? 0,
        setupPage: Boolean(document.querySelector('[data-testid="setup-page"]')),
        hero: Boolean(document.querySelector('[data-testid="hero-greeting"]')),
      },
    };
  });

async function shot(page, theme, stage) {
  const file = `${OUT}/first-run-${theme}-${stage}.png`;
  await page.screenshot({ path: file });
  facts.shots.push(file);
  return file;
}

const until = async (page, started, ms) => {
  const wait = ms - (Date.now() - started);
  if (wait > 0) await page.waitForTimeout(wait);
};

for (const theme of ['light', 'dark']) {
  // ---- the new visitor: the scene, stage by stage --------------------------------
  const { page, context, errors, started } = await open({ theme, configured: false });
  await page.waitForSelector('[data-testid="first-run-intro"]');
  const appeared = Date.now();
  const first = await stateOf(page);
  await shot(page, theme, '01-frame-one');
  check(`${theme}.dialog`, first.overlay?.role === 'dialog' && first.overlay?.modal === 'true', first.overlay);
  check(`${theme}.named-by-its-copy`, first.overlay?.labelled && first.overlay?.described, first.overlay);
  check(`${theme}.skip-in-frame-one`, first.skip !== null, first.skip);
  check(`${theme}.app-mounted-behind`, first.appBehind.rootChildren > 0, first.appBehind);
  check(`${theme}.title-not-yet-painted`, Number(first.title?.opacity) < 1, first.title);

  await until(page, appeared, 1300);
  const actionable = await stateOf(page);
  await shot(page, theme, '02-actionable');
  check(
    `${theme}.button-carries-the-sheet-delay`,
    Number.parseFloat(actionable.cta?.delay || 'NaN') === 1200,
    actionable.cta,
  );
  check(`${theme}.button-painted`, Number(actionable.cta?.opacity) === 1, actionable.cta);
  check(`${theme}.setup-page-behind`, actionable.appBehind.setupPage, actionable.appBehind);

  await until(page, appeared, 3600);
  await shot(page, theme, '03-breath');

  // The skip control, hovered: the way out is the same control in every frame.
  await page.hover('[data-testid="intro-skip"]');
  await shot(page, theme, '04-skip-hover');

  // The handover: the button ends the scene, the decay eats the overlay from the right,
  // and the surface behind it stands there afterwards.
  await page.click('[data-testid="intro-cta"]');
  await page.waitForTimeout(160);
  const leaving = await stateOf(page);
  await shot(page, theme, '05-leaving');
  check(`${theme}.decay-runs`, leaving.overlay?.phase === 'leaving', leaving.overlay);
  await page.waitForSelector('[data-testid="first-run-intro"]', { state: 'detached' });
  const after = await stateOf(page);
  await shot(page, theme, '06-handover');
  check(`${theme}.scene-gone`, after.overlay === null, after.overlay);
  check(`${theme}.setup-page-stands`, after.appBehind.setupPage, after.appBehind);
  check(
    `${theme}.flag-written`,
    await page.evaluate((key) => window.localStorage.getItem(key) !== null, SEEN_KEY),
    'localStorage',
  );

  // A reload of the same browser: the scene is gone for good.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(900);
  const reload = await stateOf(page);
  check(`${theme}.reload-shows-no-scene`, reload.overlay === null, reload.overlay);
  check(`${theme}.no-page-errors`, errors.length === 0, errors);
  await context.close();

  // ---- a viewer who asked for less motion: one still, then the app -----------------
  const still = await open({ theme, reducedMotion: 'reduce', configured: true });
  await still.page.waitForSelector('[data-testid="first-run-intro"]');
  const stillState = await stateOf(still.page);
  await shot(still.page, theme, '07-still');
  check(`${theme}.still-drawn`, stillState.overlay?.reduced === 'true', stillState.overlay);
  check(`${theme}.still-mark-settled`, stillState.overlay?.markState === 'settle', stillState.overlay);
  check(
    `${theme}.still-has-no-delays`,
    [stillState.title, stillState.cta].every((el) => el && Number.parseFloat(el.delay || '0') === 0),
    [stillState.title?.delay, stillState.cta?.delay],
  );
  await still.page.waitForSelector('[data-testid="first-run-intro"]', { state: 'detached', timeout: 6000 });
  check(`${theme}.still-closes-itself`, true, 'detached inside 6 s');
  await shot(still.page, theme, '08-still-handover');
  await still.context.close();

  // ---- a returning browser: the app, no scene --------------------------------------
  const back = await open({ theme, configured: true, seen: true });
  await back.page.waitForTimeout(1200);
  const backState = await stateOf(back.page);
  await shot(back.page, theme, '09-returning-user');
  check(`${theme}.returning-user-no-scene`, backState.overlay === null, backState.overlay);
  check(`${theme}.returning-user-in-the-app`, backState.appBehind.rootChildren > 0, backState.appBehind);
  await back.context.close();
}

await browser.close();
console.log(JSON.stringify(facts, null, 2));
if (facts.failures.length > 0) {
  console.error(`\n${facts.failures.length} failed check(s)`);
  process.exit(1);
}
