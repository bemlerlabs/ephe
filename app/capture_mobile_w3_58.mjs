// W3-58: 390 px mobile visual receipts for the five main screens.
// Harness: Playwright's bundled Chromium (CDP under the hood), same recipe as
// capture_artifacts_wd27.mjs — dsf 2, dark scheme, EN first run. The browser
// binary is passed explicitly because the local ms-playwright cache has no
// revision 1243 (the one @playwright/test 1.64.0 pins).
//
// Screens: Chat (#/), Knowledge (#/memory), Artifacts (#/artifacts),
//          Tools (#/tools), Setup (#/setup).
// Setup renders only behind a one-visit intent (sessionStorage
// 'ephe.setup_intent'); it is injected per context.
//
// Usage (backend on 8765 + vite dev on 5173 must be running):
//   cd app && node capture_mobile_w3_58.mjs
//
// The run asserts the real DOM state (anchor rendered, no horizontal
// overflow) and prints one JSON facts block; exit code 1 if any screen
// failed to render its anchor.
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const BASE = process.env.EPHE_BASE || 'http://127.0.0.1:5173';
const OUT = undefined;
const EXE =
  process.env.EPHE_CHROME ||
  undefined;

const VIEWPORT = { width: 390, height: 844 };
const CONSOLE_ERRORS = [];

mkdirSync(OUT, { recursive: true });
const facts = { base: BASE, chrome: EXE, viewport: VIEWPORT, shots: [], checks: {} };

const browser = await chromium.launch({ executablePath: EXE, headless: true });

async function newPage({ intent = false } = {}) {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });
  await context.addInitScript(
    (withIntent) => {
      // This runs in every frame, including opaque-origin ones (PDF/preview
      // iframes) where localStorage is null — guard so the harness injects
      // silently instead of throwing a pageerror into the receipt.
      try {
        localStorage.setItem('i18nextLng', 'en');
        localStorage.setItem('ephe_onboarded', '1');
      } catch {
        /* opaque origin: nothing to seed */
      }
      if (withIntent) {
        try {
          sessionStorage.setItem('ephe.setup_intent', '1');
        } catch {
          /* opaque origin */
        }
      }
    },
    intent,
  );
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  page.on('console', (m) => {
    if (m.type() === 'error') CONSOLE_ERRORS.push({ text: m.text(), loc: m.location()?.url });
  });
  page.on('pageerror', (e) => CONSOLE_ERRORS.push({ text: String(e), loc: 'pageerror' }));
  return { context, page };
}

async function shot(page, name) {
  const file = `${OUT}/${name}.png`;
  await page.screenshot({ path: file });
  facts.shots.push(file);
  console.log('shot:', file);
  return file;
}

// Horizontal-overflow probe: documentElement scrollWidth vs clientWidth, plus
// the widest offenders that actually stick out past the viewport edge. A
// mobile layout that must not scroll sideways is proven by an empty offender
// list plus zero delta.
async function readFacts(page) {
  return page.evaluate(() => {
    const de = document.documentElement;
    const vw = de.clientWidth;
    const offenders = [];
    let offCanvasLeft = 0;
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      // Right-edge overflow is what actually makes a page scroll sideways.
      if (r.right > vw + 1) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          testid: el.getAttribute('data-testid') || null,
          cls: (el.getAttribute('class') || '').slice(0, 80),
          right: Math.round(r.right),
          left: Math.round(r.left),
        });
      } else if (r.left < -1) {
        // Intentional off-canvas (the mobile drawer parks left of the frame);
        // counted, not treated as an overflow defect.
        offCanvasLeft++;
      }
    }
    const title = document.querySelector('[data-testid="page-title"]')?.textContent?.trim() ?? null;
    const subtitle =
      document.querySelector('[data-testid="page-subtitle"]')?.textContent?.trim() ?? null;
    return {
      url: location.href,
      title,
      subtitle,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      scrollWidth: de.scrollWidth,
      clientWidth: de.clientWidth,
      overflow: Math.max(0, de.scrollWidth - de.clientWidth),
      offenderCount: offenders.length,
      offenders: offenders.slice(0, 8),
      offCanvasLeft,
      // mobile shell facts (chat)
      sidebarHidden: (() => {
        const sb = document.querySelector('[data-testid="chat-sidebar"]');
        if (!sb) return null;
        return getComputedStyle(sb).display === 'none' || sb.getBoundingClientRect().width === 0;
      })(),
      hamburger: Boolean(document.querySelector('[data-testid="header-menu-toggle"]')),
      chatScroll: Boolean(document.querySelector('[data-testid="chat-scroll-region"]')),
    };
  });
}

// Screens, in the order the brief lists them. `anchor` is the root the page
// must paint; `intent` gates the setup route.
const SCREENS = [
  { key: 'chat', file: 'w3_390_chat', route: '#/', anchor: '[data-testid="chat-scroll-region"]' },
  { key: 'knowledge', file: 'w3_390_knowledge', route: '#/memory', anchor: '[data-testid="memory-page"]' },
  { key: 'artifacts', file: 'w3_390_artifacts', route: '#/artifacts', anchor: '[data-testid="artifacts-page"]' },
  { key: 'tools', file: 'w3_390_tools', route: '#/tools', anchor: '[data-testid="tools-vision"]' },
  { key: 'setup', file: 'w3_390_setup', route: '#/setup', anchor: '[data-testid="setup-page"]', intent: true },
];

for (const s of SCREENS) {
  const { context, page } = await newPage({ intent: Boolean(s.intent) });
  const errBefore = CONSOLE_ERRORS.length;
  try {
    await page.goto(`${BASE}/${s.route}`, { waitUntil: 'networkidle' });
    await page.waitForSelector(s.anchor, { timeout: 30000 });
    // framer-motion stagger + lazy chunk settle
    await page.waitForTimeout(1400);
    facts.checks[s.key] = await readFacts(page);
    facts.checks[s.key].anchor = s.anchor;
    facts.checks[s.key].consoleErrors = CONSOLE_ERRORS.slice(errBefore);
    await shot(page, s.file);
  } catch (err) {
    facts.checks[s.key] = { error: String(err), anchor: s.anchor, url: page.url() };
    try {
      await shot(page, `${s.file}_FAILED`);
    } catch {
      /* nothing to capture */
    }
  }
  await context.close();
}

await browser.close();

facts.consoleErrors = CONSOLE_ERRORS;

const rendered = SCREENS.filter((s) => facts.checks[s.key] && !facts.checks[s.key].error);
const noOverflow = SCREENS.every(
  (s) => facts.checks[s.key]?.error || (facts.checks[s.key]?.overflow ?? 1) === 0,
);
const ok = rendered.length === SCREENS.length && noOverflow;

writeFileSync(`${OUT}/facts.json`, JSON.stringify(facts, null, 2));
console.log('FACTS_JSON:', JSON.stringify(facts));
console.log(
  `rendered ${rendered.length}/${SCREENS.length} screens; no-overflow=${noOverflow}`,
);
console.log(ok ? 'W3_58_OK' : 'W3_58_FAIL');
process.exit(ok ? 0 : 1);
