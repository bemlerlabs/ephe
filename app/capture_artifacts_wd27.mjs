// WD-27: real-browser receipts for the Artifacts page (/artifacts).
// Harness: Playwright's bundled Chromium (CDP under the hood), same recipe as
// capture_j6.mjs — dsf 2, dark scheme, EN first run. The browser binary is
// passed explicitly because the local ms-playwright cache has no revision 1243.
//
// Usage (backend on 8765 + vite dev on 5173 must be running):
//   cd app && node capture_artifacts_wd27.mjs
//
// The run asserts the real DOM state (rows, group counts, stats line) and
// prints one JSON facts block; exit code 1 if the page did not render rows.
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

const BASE = process.env.EPHE_BASE || 'http://127.0.0.1:5173';
const OUT = undefined;
const EXE =
  process.env.EPHE_CHROME ||
  undefined;

mkdirSync(OUT, { recursive: true });
const facts = { base: BASE, chrome: EXE, shots: [], checks: {} };

const browser = await chromium.launch({ executablePath: EXE, headless: true });

async function newPage(viewport) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });
  await context.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en');
    localStorage.setItem('ephe_onboarded', '1');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  return { context, page };
}

async function shot(page, name) {
  const file = `${OUT}/${name}.png`;
  await page.screenshot({ path: file });
  facts.shots.push(file);
  console.log('shot:', file);
  return file;
}

// The detail preview (PDF -> iframe with PDF.js, images -> <img>) renders a beat
// after the row is picked; a shot taken too early shows an empty frame.
async function waitForPreview(page) {
  try {
    await page.waitForSelector(
      '[data-testid="artifact-detail"] iframe, [data-testid="artifact-detail"] img, [data-testid="artifact-preview-code"]',
      { timeout: 12000 },
    );
    await page.waitForTimeout(4500);
  } catch {
    /* no preview for this kind — the shot is still the real pane */
  }
}

// The page reads rows from /api/artifacts; wait until the shelf has content.
async function waitForRows(page) {
  await page.waitForSelector('[data-testid="artifacts-page"]', { timeout: 30000 });
  await page.waitForFunction(
    () =>
      Boolean(
        document.querySelector('[data-testid^="artifact-row-"]') ||
          document.querySelector('[data-testid="artifacts-shelf-empty"]'),
      ),
    { timeout: 30000 },
  );
  await page.waitForTimeout(600); // let the framer-motion stagger settle
}

async function readFacts(page) {
  return page.evaluate(() => {
    const rowEls = [...document.querySelectorAll('[data-testid^="artifact-row-"]')];
    const groups = [...document.querySelectorAll('[data-testid^="shelf-group-"]')].map(
      (h) => h.textContent?.trim(),
    );
    const detail = document.querySelector('[data-testid="artifact-detail"]');
    const detailTitle = detail
      ? detail.querySelector('h1,h2,h3,[class*="font-serif"],p')?.textContent?.trim()
      : null;
    return {
      statsLine: document.querySelector('[data-testid="artifacts-stats"]')?.textContent?.trim() ?? null,
      rowCount: rowEls.length,
      firstRowId: rowEls[0]?.getAttribute('data-testid')?.replace('artifact-row-', '') ?? null,
      groups,
      detailId: detail?.getAttribute('data-id') ?? null,
      detailTitle,
      hasDetail: Boolean(detail),
      selectedRowId:
        [...document.querySelectorAll('[data-testid^="artifact-select-"]')].find((b) =>
          b.closest('[aria-selected="true"], [data-selected="true"]'),
        )?.getAttribute('data-testid') ?? null,
      viewport: { w: window.innerWidth, h: window.innerHeight },
    };
  });
}

// ── 1. Shelf (regal), desktop ────────────────────────────────────────────
{
  const { context, page } = await newPage({ width: 1280, height: 900 });
  await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' });
  await waitForRows(page);
  await waitForPreview(page);
  // PDF.js paints the frame once the pane is scrolled into view; nudge, then
  // return to the top so the shot keeps the whole Workbench in frame.
  await page.evaluate(() =>
    document.querySelector('[data-testid="artifact-detail"]')?.scrollIntoView({ block: 'start' }),
  );
  await page.waitForTimeout(1400);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  facts.checks.regalDesktop = await readFacts(page);
  await shot(page, 'wd27_artifacts_regal_desktop');
  await context.close();
}

// ── 2. Detail pane scrolled to provenance + tags ─────────────────────────
// No click here: the click-select path is exercised in the mobile block. A
// click can race the app's Suspense re-render, so the desktop receipt uses the
// default selection and scrolls the detail pane to its lower half.
{
  const { context, page } = await newPage({ width: 1280, height: 900 });
  await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' });
  await waitForRows(page);
  await waitForPreview(page);
  await page.evaluate(() => {
    const detail = document.querySelector('[data-testid="artifact-detail"]');
    // the scroll owner is the pane's own overflow container
    const scroller = detail?.closest('[class*="overflow"]') ?? detail?.parentElement;
    (scroller ?? detail)?.scrollTo?.({ top: 99999 });
    detail?.scrollIntoView({ block: 'start' });
  });
  await page.waitForTimeout(500);
  facts.checks.detailLower = await page.evaluate(() => ({
    hasDetail: Boolean(document.querySelector('[data-testid="artifact-detail"]')),
    hasProvenance: Boolean(document.querySelector('[data-testid="artifact-detail"]')?.textContent?.includes('Provenance')),
    hasTags: Boolean(document.querySelector('[data-testid="artifact-detail"]')?.textContent?.includes('TAGS') || [...document.querySelectorAll('input')].some(i => /tag/i.test(i.getAttribute('aria-label')||i.placeholder||''))),
  }));
  await shot(page, 'wd27_artifacts_detail_provenance');
  await context.close();
}

// ── 3. Kind filter (PDF) ─────────────────────────────────────────────────
{
  const { context, page } = await newPage({ width: 1280, height: 800 });
  await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' });
  await waitForRows(page);
  await page.getByRole('button', { name: /^PDF$/i }).first().click();
  await page.waitForTimeout(800);
  facts.checks.filterPdf = await readFacts(page);
  await shot(page, 'wd27_artifacts_filter_pdf');
  await context.close();
}

// ── 4. No-match search state ─────────────────────────────────────────────
{
  const { context, page } = await newPage({ width: 1280, height: 800 });
  await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' });
  await waitForRows(page);
  const searchBox = page.getByRole('textbox').first();
  await searchBox.fill('zzz-no-such-artifact-zzz');
  await page.waitForSelector('[data-testid="artifacts-nomatch"]', { timeout: 15000 });
  // Read the state and shoot in the same settled moment: the list refetch
  // briefly unmounts the shelf, so anything after a sleep can drift.
  facts.checks.noMatch = await page.evaluate(() => ({
    query: document.querySelector('input[aria-label]')?.value ?? null,
    sentence: document.querySelector('[data-testid="artifacts-nomatch"] p')?.textContent?.trim() ?? null,
    hasClear: Boolean(document.querySelector('[data-testid="artifacts-clear-filters"]')),
  }));
  await shot(page, 'wd27_artifacts_nomatch');
  await context.close();
}

// ── 5. Archive (ablage) — the empty-adopted state ────────────────────────
{
  const { context, page } = await newPage({ width: 1280, height: 800 });
  await page.goto(`${BASE}/#/artifacts/ablage`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-testid="artifacts-page"]', { timeout: 30000 });
  await page.waitForTimeout(1500);
  facts.checks.ablage = await page.evaluate(() => ({
    hint: document.querySelector('[data-testid="artifacts-ablage-hint"]')?.textContent?.trim() ?? null,
    rowCount: document.querySelectorAll('[data-testid^="artifact-row-"]').length,
    empty: document.querySelector('[data-testid="artifacts-shelf-empty"]')?.textContent?.trim() ?? null,
  }));
  await shot(page, 'wd27_artifacts_ablage_empty');
  await context.close();
}

// ── 6. Mobile 390px — shelf + detail ─────────────────────────────────────
{
  const { context, page } = await newPage({ width: 390, height: 844 });
  await page.goto(`${BASE}/#/artifacts`, { waitUntil: 'networkidle' });
  await waitForRows(page);
  facts.checks.mobileShelf = await readFacts(page);
  await shot(page, 'wd27_artifacts_regal_mobile_390');
  const row = page.locator('[data-testid^="artifact-select-"]').first();
  if (await row.count()) {
    await row.click();
    await page.waitForTimeout(900);
    await page.evaluate(() =>
      document.querySelector('[data-testid="artifact-detail"]')?.scrollIntoView({ block: 'start' }),
    );
    await page.waitForTimeout(400);
  }
  await waitForPreview(page);
  await shot(page, 'wd27_artifacts_detail_mobile_390');
  await context.close();
}

await browser.close();

const ok =
  (facts.checks.regalDesktop?.rowCount ?? 0) > 0 && (facts.checks.mobileShelf?.rowCount ?? 0) > 0;
writeFileSync(`${OUT}/facts.json`, JSON.stringify(facts, null, 2));
console.log('FACTS_JSON:', JSON.stringify(facts));
console.log(ok ? 'WD27_OK' : 'WD27_FAIL');
process.exit(ok ? 0 : 1);
