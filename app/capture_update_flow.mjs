// Update-flow harness — the states the owner asked for, captured without a
// newer release in the feed.
//
// Three stubs stand in for the three external things:
//   1. GET /api/update/check  → fulfilled by Playwright with a fixture that
//      announces 0.1.0-beta.2 as available (the live feed would have to publish
//      a release for this to happen for real).
//   2. @tauri-apps/plugin-updater → fulfilled with a stub ESM module, so the
//      desktop download/install path runs in a plain Chromium: Started, chunked
//      Progress every 120 ms, then install(), then done. window.__TAURI__ is
//      injected in an init script, which is what makes the surface take the
//      desktop branch.
//   3. window.__TAURI__.process.relaunch → the restart the plugin global would
//      perform is recorded instead of run, so a capture never restarts the
//      browser and the run can assert that the click reached the shell.
//
// Usage (vite dev on 5173 must be running; the backend is not needed, since the
// check endpoint is fulfilled by the harness):
//   cd app && npm run dev            # in one shell
//   cd app && node capture_update_flow.mjs
//
// Optional: EPHE_BASE (default http://127.0.0.1:5173), EPHE_CHROME (browser
// binary), EPHE_OUT (screenshot directory).
//
// The run asserts the real DOM: the signal is a running animation on the header
// button and a settled one on hover, the bar reports the percentage it was
// given, the installing phase is a phase of its own, the details carry the
// release's own words, the restart reaches the process global, and reduced
// motion leaves every animated element of the chain standing still.
// Every check prints one JSON fact; exit code 1 if any of them failed.
import { chromium } from '@playwright/test';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';

const BASE = process.env.EPHE_BASE || 'http://127.0.0.1:5173';
const OUT = process.env.EPHE_OUT || 'test-results/update-flow';
const CACHED_CHROME =
  undefined;
const EXE = process.env.EPHE_CHROME || (existsSync(CACHED_CHROME) ? CACHED_CHROME : undefined);

const VIEWPORT = { width: 1280, height: 820 };
const CFG = { total: 4_000_000, chunks: 10, chunkMs: 120, installMs: 2_500 };

mkdirSync(OUT, { recursive: true });
const facts = { base: BASE, chrome: EXE || 'bundled chromium', shots: [], signal: {}, progress: {}, reduced: {} };

/** The answer the check endpoint would give once a release exists. */
const CHECK_FIXTURE = {
  enabled: true,
  available: true,
  current: '0.1.0-beta.1',
  latest: '0.1.0-beta.2',
  url: 'https://example.invalid/ephe/releases',
  notes: 'Harness fixture: the download path is exercised from here.',
};

/** Stand-in for @tauri-apps/plugin-updater. Reports the whole download, chunk by
 *  chunk, so the bar has something to follow. `total` false = a source that
 *  announces no content length, which is the indeterminate case. */
const updaterStub = (withTotal) => `
const listeners = [];
export async function check() {
  return {
    available: true,
    version: '0.1.0-beta.2',
    currentVersion: '0.1.0-beta.1',
    rawJson: { url: 'https://example.invalid/ephe/Ephe_0.1.0-beta.2_aarch64.app.tar.gz' },
    async download(onEvent) {
      const total = ${withTotal ? CFG.total : 'undefined'};
      if (onEvent) onEvent({ event: 'Started', data: { contentLength: total } });
      const share = total ? total / ${CFG.chunks} : 0;
      for (let i = 0; i < ${CFG.chunks}; i++) {
        await new Promise((r) => setTimeout(r, ${CFG.chunkMs}));
        if (onEvent) onEvent({ event: 'Progress', data: { chunkLength: share } });
      }
      if (onEvent) onEvent({ event: 'Finished' });
      listeners.push('downloaded');
    },
    async install() {
      await new Promise((r) => setTimeout(r, ${CFG.installMs}));
      listeners.push('installed');
    },
  };
}
export default { check };
`;

const processStub = `
const listeners = [];
export async function relaunch() { listeners.push('relaunched'); }
export default { relaunch };
`;

const browser = await chromium.launch({ ...(EXE ? { executablePath: EXE } : {}), headless: true });

async function open({ reducedMotion = 'no-preference', withTotal = true } = {}) {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    colorScheme: 'dark',
    reducedMotion,
  });
  await context.addInitScript(() => {
    // The desktop branch, plus the two flags the first-run screens read. The
    // restart is stubbed here: the capture must never restart the browser, and
    // every call the surface would have made is recorded for the assertions.
    window.__IPC__ = [];
    window.__TAURI__ = {
      event: { listen: async () => () => {} },
      process: {
        relaunch: async () => {
          window.__IPC__.push('process.relaunch');
        },
      },
      core: {
        invoke: async (cmd) => {
          window.__IPC__.push(cmd);
          return null;
        },
      },
    };
    try {
      localStorage.setItem('i18nextLng', 'de');
      localStorage.setItem('ephe_onboarded', '1');
    } catch {
      /* opaque origin */
    }
  });
  const page = await context.newPage();
  await page.route(
    (url) => url.pathname.endsWith('/api/update/check'),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(CHECK_FIXTURE),
      }),
  );
  await page.route(
    (url) => url.href.includes('plugin-updater'),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/javascript',
        body: updaterStub(withTotal),
      }),
  );
  await page.route(
    (url) => url.href.includes('plugin-process'),
    (route) =>
      route.fulfill({ status: 200, contentType: 'application/javascript', body: processStub }),
  );
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  return { context, page };
}

async function motion(page, selector, pseudo = null) {
  return page.evaluate(
    ([sel, ps]) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const cs = getComputedStyle(el, ps || undefined);
      return {
        animationName: cs.animationName,
        animationDuration: cs.animationDuration,
        animationTimingFunction: cs.animationTimingFunction,
        animationIterationCount: cs.animationIterationCount,
        transitionProperty: cs.transitionProperty,
        transitionDuration: cs.transitionDuration,
        transitionTimingFunction: cs.transitionTimingFunction,
        opacity: cs.opacity,
        transform: cs.transform,
        filter: cs.filter,
        color: cs.color,
      };
    },
    [selector, pseudo],
  );
}

const shot = async (page, name, clip) => {
  const path = `${OUT}/${name}.png`;
  await page.screenshot({ path, ...(clip ? { clip } : {}) });
  facts.shots.push(path);
  return path;
};

const checks = {};
const expect = (name, ok, detail) => {
  checks[name] = ok ? 'ok' : `FAILED: ${detail}`;
  if (!ok) console.error(`✗ ${name}: ${detail}`);
  else console.log(`✓ ${name}`);
};

// ── Pass 1: the determinate download, on the animated surface ───────────────
{
  const { context, page } = await open();
  const button = page.locator('[data-testid="header-update"]');
  await button.waitFor({ state: 'visible', timeout: 20000 });
  await page.waitForSelector('[data-testid="header-update"][data-signal="available"]', {
    timeout: 20000,
  });
  const box = await button.boundingBox();
  await shot(page, '1-signal-available', {
    x: Math.max(0, box.x - 24),
    y: Math.max(0, box.y - 24),
    width: box.width + 48,
    height: box.height + 48,
  });

  const halo = await motion(page, '[data-testid="header-update"]', '::after');
  const glyph = await motion(page, '[data-testid="header-update"] svg');
  const running = await page.evaluate(
    () =>
      document
        .querySelector('[data-testid="header-update"]')
        .getAnimations({ subtree: true })
        .filter((a) => a.playState === 'running').length,
  );
  facts.signal = { halo, glyph, runningAnimations: running };
  expect(
    'the header affordance animates on its own',
    halo?.animationName === 'update-signal-halo' &&
      halo?.animationDuration === '3.2s' &&
      halo?.animationIterationCount === 'infinite' &&
      glyph?.animationName === 'update-signal-glow',
    JSON.stringify({ halo, glyph }),
  );

  // Two frames three quarters of a period apart prove the signal moves.
  const seen = new Set();
  for (let i = 0; i < 6; i++) {
    const cs = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="header-update"]');
      return getComputedStyle(el, '::after').opacity;
    });
    seen.add(cs);
    await page.waitForTimeout(350);
  }
  facts.signal.haloOpacitySamples = [...seen];
  expect('the halo is a breath, not a constant', seen.size > 1, [...seen].join(','));

  // U-4: the hover settles the breath and takes the brand tint — the same one
  // curve the breath reads at. The pointer leaves before the click, so the
  // dialog opens from the resting state.
  await button.hover();
  await page.waitForTimeout(150);
  const hoverHalo = await motion(page, '[data-testid="header-update"]', '::after');
  const hoverGlyph = await motion(page, '[data-testid="header-update"] svg');
  const hoverTint = await page.evaluate(
    () => getComputedStyle(document.querySelector('[data-testid="header-update"]')).backgroundColor,
  );
  facts.hover = { halo: hoverHalo, glyph: hoverGlyph, tint: hoverTint };
  const hbox = await button.boundingBox();
  await shot(page, '1b-signal-hover', {
    x: Math.max(0, hbox.x - 24),
    y: Math.max(0, hbox.y - 24),
    width: hbox.width + 48,
    height: hbox.height + 48,
  });
  expect(
    'the hover settles the breath and takes the brand tint',
    hoverHalo?.animationName === 'none' &&
      hoverHalo?.opacity === '0.9' &&
      hoverGlyph?.animationName === 'none' &&
      String(hoverGlyph?.filter).includes('drop-shadow') &&
      hoverTint !== 'rgba(0, 0, 0, 0)',
    JSON.stringify({ hoverHalo, hoverGlyph, tint: hoverTint }),
  );
  await page.mouse.move(0, 0);
  await page.waitForTimeout(120);

  await button.click();
  await page.waitForSelector('[data-testid="update-dialog"][data-phase="available"]');
  // Every phase the dialog takes is written down by its own DOM, so a slow
  // screenshot round-trip cannot lose one: the assertions read that record, and
  // a capture happens while the phase is on screen.
  await page.evaluate(() => {
    window.__phases = [];
    let last = null;
    const read = () => {
      const el = document.querySelector('[data-testid="update-dialog"]');
      if (!el || el.dataset.phase === last) return;
      last = el.dataset.phase;
      window.__phases.push(last);
    };
    read();
    new MutationObserver(read).observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ['data-phase'],
    });
  });
  await page.waitForTimeout(250);
  await shot(page, '2-dialog-available');

  // U-4: the Details block — closed first, then opened. Its rows carry the
  // release's own words and the facts the transfer reported.
  const detailsClosed = await page.evaluate(() => {
    const d = document.querySelector('[data-testid="update-details"]');
    return {
      open: d.open,
      notes: document.querySelector('[data-testid="update-details-notes"]')?.textContent || '',
      version: document.querySelector('[data-testid="update-details-version"]')?.textContent || '',
    };
  });
  await page.click('[data-testid="update-details"] > summary');
  await page.waitForTimeout(250);
  const detailsOpen = await page.evaluate(() => {
    const d = document.querySelector('[data-testid="update-details"]');
    const body = document.querySelector('.update-details-body');
    return {
      open: d.open,
      bodyAnimation: getComputedStyle(body).animationName,
      caret: getComputedStyle(document.querySelector('.update-caret')).transform,
    };
  });
  facts.details = { closed: detailsClosed, opened: detailsOpen };
  await shot(page, '2b-details-open');
  expect(
    'the details carry the release notes and open in one step',
    detailsClosed.open === false &&
      detailsClosed.notes.length > 0 &&
      detailsOpen.open === true &&
      detailsOpen.bodyAnimation === 'update-details-reveal',
    JSON.stringify({ detailsClosed, detailsOpen }),
  );

  await page.click('[data-testid="update-install"]');

  const samples = [];
  let installing = null;
  let determinateShot = false;
  const deadline = Date.now() + 25000;
  while (Date.now() < deadline) {
    const now = await page.evaluate(() => {
      const bar = document.querySelector('[data-testid="update-progress"]');
      const pct = document.querySelector('[data-testid="update-percent"]');
      return {
        phase: document.querySelector('[data-testid="update-dialog"]')?.dataset.phase,
        value: bar?.getAttribute('aria-valuenow'),
        text: pct?.textContent || null,
      };
    });
    if (now.phase === 'ready') break;
    if (now.phase === 'installing' && !installing) {
      installing = { percent: now.text, value: now.value };
      await shot(page, '4-installing');
    }
    if (now.phase === 'downloading' && now.value !== null && now.value !== undefined) {
      samples.push(Number(now.value));
      if (samples.length === 4 && !determinateShot) {
        determinateShot = true;
        facts.progress.transition = await motion(page, '[data-testid="update-progress-fill"]');
        await shot(page, '3-downloading');
      }
    }
    await page.waitForTimeout(40);
  }
  const phases = await page.evaluate(() => window.__phases);
  facts.progress.samples = samples;
  facts.progress.phases = phases;
  facts.progress.installing = installing;
  expect(
    'the bar follows the reported share',
    samples.length >= 3 && samples[0] < samples[samples.length - 1],
    samples.join(' -> '),
  );
  expect(
    'the running phases are the ones that happened, in order',
    phases.includes('downloading') &&
      phases.indexOf('downloading') < phases.indexOf('installing') &&
      phases.indexOf('installing') < phases.indexOf('ready'),
    phases.join(' -> '),
  );
  expect(
    'the installing phase is its own state',
    !!installing && installing.percent !== null && String(installing.percent).trim().length > 0,
    JSON.stringify(installing),
  );

  await page.waitForSelector('[data-testid="update-dialog"][data-phase="ready"]', {
    timeout: 15000,
  });
  const ready = await page.evaluate(() => {
    const icon = document.querySelector('[data-testid="update-dialog"] svg.update-confirm');
    return {
      hasIcon: !!icon,
      animation: icon ? getComputedStyle(icon).animationName : null,
      relaunch: !!document.querySelector('[data-testid="update-relaunch"]'),
    };
  });
  facts.ready = ready;
  await shot(page, '5-ready');
  expect(
    'the finish confirms itself and offers the restart',
    ready.hasIcon && ready.relaunch,
    JSON.stringify(ready),
  );

  // U-4: the restart reaches the process global the plugin defines and the stub
  // records the call. Nothing may actually reload.
  const restartBefore = await page.evaluate(() => (window.__IPC__ || []).length);
  const urlBefore = page.url();
  await page.click('[data-testid="update-relaunch"]');
  await page.waitForTimeout(250);
  const restartAfter = await page.evaluate(() => window.__IPC__);
  const called = restartAfter.slice(restartBefore);
  const dialogAfter = await page.evaluate(
    () => !!document.querySelector('[data-testid="update-dialog"]'),
  );
  facts.restart = {
    called,
    urlUnchanged: page.url() === urlBefore,
    dialogStillThere: dialogAfter,
  };
  await shot(page, '5b-restart');
  expect(
    'the restart goes through the process global and nothing restarts here',
    called.includes('process.relaunch') &&
      !called.includes('plugin:process|restart') &&
      facts.restart.urlUnchanged &&
      dialogAfter,
    JSON.stringify(facts.restart),
  );

  facts.progress.transitionAtStart = await motion(page, '[data-testid="update-progress-fill"]');
  await context.close();
}

// ── Pass 2: a source that reports no total ──────────────────────────────────
{
  const { context, page } = await open({ withTotal: false });
  await page.waitForSelector('[data-testid="header-update"][data-signal="available"]', {
    timeout: 20000,
  });
  await page.click('[data-testid="header-update"]');
  await page.click('[data-testid="update-install"]');
  await page.waitForSelector('[data-testid="update-progress"][data-indeterminate="true"]', {
    timeout: 15000,
  });
  const band = await page.evaluate(() => {
    const fill = document.querySelector('[data-testid="update-progress-fill"]');
    const bar = document.querySelector('[data-testid="update-progress"]');
    return {
      animationName: getComputedStyle(fill).animationName,
      animationDuration: getComputedStyle(fill).animationDuration,
      animationTimingFunction: getComputedStyle(fill).animationTimingFunction,
      ariaValuenow: bar.getAttribute('aria-valuenow'),
      percentLine: !!document.querySelector('[data-testid="update-percent"]'),
    };
  });
  facts.indeterminate = band;
  await page.waitForTimeout(300);
  await shot(page, '6-downloading-no-total');
  expect(
    'a source without a total gets the band and no number',
    band.animationName === 'update-progress-sweep' &&
      band.animationDuration === '1.4s' &&
      band.ariaValuenow === null &&
      band.percentLine === false,
    JSON.stringify(band),
  );
  await context.close();
}

// ── Pass 3: reduced motion — the signal stands still and stays lit ──────────
{
  const { context, page } = await open({ reducedMotion: 'reduce' });
  await page.waitForSelector('[data-testid="header-update"][data-signal="available"]', {
    timeout: 20000,
  });
  const still = await page.evaluate(() => {
    const el = document.querySelector('[data-testid="header-update"]');
    return {
      halo: getComputedStyle(el, '::after').animationName,
      haloOpacity: getComputedStyle(el, '::after').opacity,
      glyphAnimation: getComputedStyle(el.querySelector('svg')).animationName,
      glyphFilter: getComputedStyle(el.querySelector('svg')).filter,
      glyphColor: getComputedStyle(el.querySelector('svg')).color,
    };
  });
  facts.reduced = { prefersReducedMotion: still };

  // The deep setting (appearance.animations_enabled = off) reaches the same
  // still state through html.no-motion.
  const switchedOff = await page.evaluate(() => {
    document.documentElement.classList.add('no-motion');
    const el = document.querySelector('[data-testid="header-update"]');
    return {
      halo: getComputedStyle(el, '::after').animationName,
      glyphAnimation: getComputedStyle(el.querySelector('svg')).animationName,
      glyphFilter: getComputedStyle(el.querySelector('svg')).filter,
    };
  });
  facts.reduced.deepSetting = switchedOff;
  const svgBox = await page.locator('[data-testid="header-update"]').boundingBox();
  await shot(page, '7-reduced-motion', {
    x: Math.max(0, svgBox.x - 24),
    y: Math.max(0, svgBox.y - 24),
    width: svgBox.width + 48,
    height: svgBox.height + 48,
  });
  expect(
    'reduced motion keeps the signal visible and standing still',
    still.halo === 'none' &&
      still.glyphAnimation === 'none' &&
      still.glyphFilter.includes('drop-shadow') &&
      switchedOff.halo === 'none' &&
      switchedOff.glyphAnimation === 'none',
    JSON.stringify({ still, switchedOff }),
  );
  await context.close();
}

// ── Pass 4: reduced motion — every animated element of the chain stands still ─
{
  const { context, page } = await open({ reducedMotion: 'reduce', withTotal: false });
  await page.waitForSelector('[data-testid="header-update"][data-signal="available"]', {
    timeout: 20000,
  });
  await page.click('[data-testid="header-update"]');
  await page.waitForSelector('[data-testid="update-dialog"][data-phase="available"]');
  await page.click('[data-testid="update-details"] > summary');
  await page.waitForTimeout(120);
  const dialogStill = await page.evaluate(() => {
    const el = document.querySelector('[data-testid="header-update"]');
    const caret = document.querySelector('.update-caret');
    return {
      haloAnimation: getComputedStyle(el, '::after').animationName,
      glyphAnimation: getComputedStyle(el.querySelector('svg')).animationName,
      caretTransition: getComputedStyle(caret).transitionDuration,
      bodyAnimation: getComputedStyle(document.querySelector('.update-details-body')).animationName,
    };
  });
  await page.click('[data-testid="update-install"]');
  await page.waitForSelector('[data-testid="update-progress"][data-indeterminate="true"]', {
    timeout: 15000,
  });
  const bandStill = await page.evaluate(() => {
    const fill = document.querySelector('[data-testid="update-progress-fill"]');
    const track = document.querySelector('[data-testid="update-progress"]');
    const cs = getComputedStyle(fill);
    return {
      animationName: cs.animationName,
      opacity: cs.opacity,
      fillsTrack:
        fill.getBoundingClientRect().width >= track.getBoundingClientRect().width - 1,
    };
  });
  await page.waitForSelector('[data-testid="update-dialog"][data-phase="ready"]', { timeout: 25000 });
  await page.click('[data-testid="update-details"] > summary');
  await page.waitForTimeout(120);
  const confirmStill = await page.evaluate(() => {
    const icon = document.querySelector('[data-testid="update-dialog"] svg.update-confirm');
    return icon ? getComputedStyle(icon).animationName : 'missing';
  });
  await shot(page, '8-reduced-motion-dialog');
  facts.reduced.dialog = { ...dialogStill, band: bandStill, confirm: confirmStill };
  expect(
    'every animated element of the chain stands still under reduced motion',
    dialogStill.haloAnimation === 'none' &&
      dialogStill.glyphAnimation === 'none' &&
      dialogStill.caretTransition === '0s' &&
      dialogStill.bodyAnimation === 'none' &&
      bandStill.animationName === 'none' &&
      bandStill.opacity === '0.35' &&
      bandStill.fillsTrack &&
      confirmStill === 'none',
    JSON.stringify(facts.reduced.dialog),
  );
  await context.close();
}

await browser.close();
facts.checks = checks;
const failed = Object.entries(checks).filter(([, v]) => v !== 'ok');
const report = `${OUT}/facts.json`;
writeFileSync(report, `${JSON.stringify(facts, null, 2)}\n`);
console.log(JSON.stringify({ report, shots: facts.shots, checks, failed: failed.length }, null, 2));
if (failed.length) process.exit(1);
