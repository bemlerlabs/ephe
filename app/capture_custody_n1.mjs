// n1-demo — the chain-of-custody evidence shots (desktop dsf2 dark, plus a 390px read).
// Run against the lane's own server: python run_server.py --port 9229 (binds 9230 here).
import { chromium } from 'playwright';

const BASE = process.env.EPHE_BASE ?? 'http://127.0.0.1:9230';
const SHOTS = undefined;
const MOVED = 'cs-20261014T142110Z-9e79f6c6';   // signed, then the bytes moved
const LANDED = 'cs-20261014T142110Z-c1b12a50';  // signed, landed atomically

// The lane's Playwright resolves a headless-shell revision this machine does not carry;
// the installed full Chromium is the one the other capture scripts in this folder name.
const EXE =
  undefined;

const browser = await chromium.launch({ executablePath: EXE, headless: true });

async function open(viewport) {
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
  page.setDefaultTimeout(45000);
  return { context, page };
}

async function shot(page, name, selector) {
  if (selector) await page.waitForSelector(selector, { timeout: 45000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SHOTS}/${name}.png` });
  console.log('shot:', `${SHOTS}/${name}.png`);
}

// 1. The moment: a signed record whose bytes moved.
{
  const { context, page } = await open({ width: 1280, height: 900 });
  await page.goto(`${BASE}/#/workspaces/change/${MOVED}`, { waitUntil: 'networkidle' });
  await shot(page, 'n1-demo-1-the-bytes-moved', '[data-testid="custody-page"]');
  console.log('refusal:', await page.textContent('[data-testid="custody-refusal-sentence"]'));

  // 2. The forbidden signature, filed for real.
  await page.click('[data-testid="custody-try-sign"]');
  await shot(page, 'n1-demo-2-the-gate-says-no', '[data-testid="custody-try-refusal"]');
  console.log('gate:', await page.textContent('[data-testid="custody-try-refusal"]'));
  console.log('can sign:', await page.textContent('[data-testid="custody-custodians"]'));
  await context.close();
}

// 3. The same page on a record that can land.
{
  const { context, page } = await open({ width: 1280, height: 900 });
  await page.goto(`${BASE}/#/workspaces/change/${LANDED}`, { waitUntil: 'networkidle' });
  await shot(page, 'n1-demo-3-signed-and-landable', '[data-testid="custody-page"]');
  console.log('landable:', await page.textContent('[data-testid="custody-landable"]'));
  await context.close();
}

// 4. The entry point on the workspaces page, and 5. the moment at 390px.
{
  const { context, page } = await open({ width: 1280, height: 900 });
  await page.goto(`${BASE}/#/workspaces`, { waitUntil: 'networkidle' });
  await page.waitForSelector(`[data-testid="changeset-custody-${MOVED}"]`, { timeout: 45000 });
  await shot(page, 'n1-demo-4-the-entry-point');
  await context.close();
}
{
  const { context, page } = await open({ width: 390, height: 844 });
  await page.goto(`${BASE}/#/workspaces/change/${MOVED}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-testid="custody-page"]', { timeout: 45000 });
  await page.click('[data-testid="custody-try-sign"]');
  await page.waitForSelector('[data-testid="custody-try-refusal"]', { timeout: 45000 });
  await shot(page, 'n1-demo-5-mobile-390');
  await context.close();
}

await browser.close();
