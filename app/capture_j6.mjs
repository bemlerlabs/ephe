// J6 AskUserQuestion gate: desktop + 390px evidence shots (v4 recipe: dsf2, dark, DE init)
import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:5173';
const SHOTS = undefined;
const EXE = undefined;

const browser = await chromium.launch({ executablePath: EXE, headless: true });

async function capture(name, viewport) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    colorScheme: 'dark',
  });
  await context.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'de');
    localStorage.setItem('ephe_onboarded', '1');
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' });
  await page.waitForSelector('#ephe-chat-input', { timeout: 25000 });

  await page.click('#ephe-chat-input');
  await page.keyboard.type(
    'Wähle ein Theme: A) Black Forest B) Nord. Nutze den json-Block mit question/options/recommendation.',
    { delay: 8 },
  );
  await page.keyboard.press('Enter');

  // wait for the card (the done event)
  let found = false;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(1000);
    found = await page.evaluate(
      () => Boolean(document.querySelector('[data-testid="ask-card"]')),
    );
    if (found) break;
  }
  console.log(`${name}: ask-card found =`, found);
  // Bring the card into view (the chat container is the scroll owner)
  await page.evaluate(() => {
    const card = document.querySelector('[data-testid="ask-card"]');
    if (card) card.scrollIntoView({ block: 'center' });
  });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SHOTS}/${name}.png` });
  console.log('shot:', `${SHOTS}/${name}.png`);
  await context.close();
}

await capture('j6_ask_desktop', { width: 1280, height: 800 });
await capture('j6_ask_mobile_390', { width: 390, height: 844 });
await browser.close();
